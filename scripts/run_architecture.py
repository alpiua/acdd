#!/usr/bin/env python3
"""Fail-closed concurrent architecture/v1 runner."""
from __future__ import annotations
import argparse, concurrent.futures, json, os, re, subprocess, sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
import yaml
from acdd_fingerprint import (
    G0_BASELINE_SECTION,
    TASK_OPTIONAL_SEMANTIC_SECTIONS,
    TASK_SEMANTIC_SECTIONS,
    architecture_amendment_fingerprint,
    architecture_authority_ids,
    architecture_code_snapshot_entries,
    fingerprint_architecture_candidate,
    fingerprint_architecture_code_inputs,
    markdown_sections,
    parse_architecture_amendments,
    parse_inputs,
    semantic_task_fingerprint,
)
from architecture_governor import (
    ArchitectureAttempt,
    ArchitectureGovernorError,
    parse_architecture_admission,
    validate_architecture_admission,
    validate_retry_admission,
)
from architecture_verification import DISCOVERY_CAPABILITIES, ArchitectureVerificationError, load_yaml, validate_contract, validate_partition_output, validate_result
from record_proof import redact_secrets
from validate_acdd import ContractError, _adapter_args, load_adapter, load_core
from value_domains import parse_value_domains

class RunnerError(RuntimeError):
    def __init__(self,message,retry_payload=None,findings=None,partitions=None):
        super().__init__(message)
        self.retry_payload=retry_payload
        self.findings=list(findings or [])
        self.partitions=list(partitions or [])

LAUNCH_TIMEOUT_SECONDS = 3600
MAX_LAUNCH_OUTPUT_BYTES = 8 * 1024 * 1024

def _text(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)

def _bounded_text(value, limit=MAX_LAUNCH_OUTPUT_BYTES):
    text = _text(value)
    if len(text.encode("utf-8")) <= limit:
        return text
    encoded = text.encode("utf-8")[-limit:]
    return "[truncated from oversized launcher output]\n" + encoded.decode("utf-8", errors="replace")

def _output_too_large(*values):
    return sum(len(_text(value).encode("utf-8")) for value in values) > MAX_LAUNCH_OUTPUT_BYTES
def utc(): return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00","Z")
def log(message): print(f"[architecture {utc()}] {message}",file=sys.stderr,flush=True)
def fence(): return chr(96) * 3
def decode_launcher_event(text):
    value=text.strip()
    if value.startswith("```"):
        value=re.sub(r"^\`\`\`(?:json)?\s*|\s*\`\`\`$","",value,flags=re.I)
    try: return json.loads(value)
    except json.JSONDecodeError: return None
def launcher_transport_error(values):
    errors=[]
    def scan(value):
        if isinstance(value,dict):
            for key in ("errorMessage","finalError"):
                message=value.get(key)
                if isinstance(message,str) and message.strip():
                    errors.append(message.strip())
            error=value.get("error")
            if isinstance(error,str) and error.strip():
                errors.append(error.strip())
            elif isinstance(error,dict):
                message=error.get("message")
                if isinstance(message,str) and message.strip():
                    errors.append(message.strip())
            for nested in value.values(): scan(nested)
        elif isinstance(value,list):
            for nested in value: scan(nested)
    for value in values: scan(value)
    if not errors: return None
    message,_=redact_secrets(errors[-1].replace("\n"," ")[:512])
    return message
def parse_launcher_output(output, required=()):
    required_set=set(required); roots=[]
    whole=decode_launcher_event(output)
    if whole is not None: roots.append(whole)
    for block in re.findall(r"```(?:json)?\s*(.*?)```",output,flags=re.I|re.S):
        value=decode_launcher_event(block)
        if value is not None: roots.append(value)
    for line in output.splitlines():
        value=decode_launcher_event(line)
        if value is not None: roots.append(value)
    def candidates(value):
        if isinstance(value,dict):
            yield value
            for nested in value.values(): yield from candidates(nested)
        elif isinstance(value,list):
            for nested in value: yield from candidates(nested)
        elif isinstance(value,str) and value.strip().startswith(("{","[","```")):
            nested=decode_launcher_event(value)
            if nested is not None and nested != value: yield from candidates(nested)
    matches=[item for root_value in roots for item in candidates(root_value) if required_set<=set(item)]
    if not matches:
        transport_error=launcher_transport_error(roots)
        if transport_error:
            raise RunnerError(f"launcher transport failure: {transport_error}")
        raise RunnerError("launcher did not return the required JSON object")
    return max(matches,key=lambda item:(len(item),len(json.dumps(item,sort_keys=True))))

USAGE_FIELDS=("input","output","cacheRead","cacheWrite","cost")
def parse_launcher_usage(output):
    totals={field:0 for field in USAGE_FIELDS}; available=False
    def normalized_usage(value):
        if not isinstance(value,dict): return None
        cost=value.get("cost",value.get("total_cost",0))
        if isinstance(cost,dict): cost=cost.get("total",0)
        input_details=value.get("input_tokens_details")
        cached_tokens=input_details.get("cached_tokens",0) if isinstance(input_details,dict) else 0
        return {
            "input":value.get("input",value.get("input_tokens",0)),
            "output":value.get("output",value.get("output_tokens",0)),
            "cacheRead":value.get("cacheRead",value.get("cache_read_tokens",cached_tokens)),
            "cacheWrite":value.get("cacheWrite",value.get("cache_write_tokens",0)),
            "cost":cost,
        }
    try:
        whole=json.loads(output)
        events=[whole] if isinstance(whole,dict) else []
    except json.JSONDecodeError:
        events=[]
        for line in output.splitlines():
            try: event=json.loads(line)
            except json.JSONDecodeError: continue
            if isinstance(event,dict): events.append(event)
    for event in events:
        if not isinstance(event,dict): continue
        usage=None
        if event.get("type")=="message_end":
            message=event.get("message")
            if isinstance(message,dict) and message.get("role")=="assistant":
                usage=normalized_usage(message.get("usage"))
        elif isinstance(event.get("usage"),dict):
            usage=normalized_usage(event["usage"])
        elif isinstance(event.get("response"),dict):
            usage=normalized_usage(event["response"].get("usage"))
        if usage is None: continue
        available=True
        for field in ("input","output","cacheRead","cacheWrite"):
            value=usage.get(field,0)
            if isinstance(value,(int,float)) and not isinstance(value,bool) and value>=0:
                totals[field]+=value
        cost=usage.get("cost",0)
        if isinstance(cost,(int,float)) and not isinstance(cost,bool) and cost>=0:
            totals["cost"]+=cost
    totals["totalTokens"]=sum(totals[field] for field in USAGE_FIELDS if field!="cost")
    return {"available":available,**totals}

def summarize_usage(records):
    fields=(*USAGE_FIELDS,"totalTokens")
    return {
        "launches":sorted(records,key=lambda item:(item["role"],item["partition"],item["attempt"])),
        "totals":{field:sum(item[field] for item in records) for field in fields},
    }

def semantic_candidate_authority(text, amendment_id=None):
    sections=markdown_sections(text)
    if G0_BASELINE_SECTION in sections:
        baseline={G0_BASELINE_SECTION:sections[G0_BASELINE_SECTION].strip()}
    else:
        baseline={
            name:sections[name].strip()
            for name in TASK_SEMANTIC_SECTIONS+TASK_OPTIONAL_SEMANTIC_SECTIONS
            if name in sections
        }
    if amendment_id is None:
        return baseline
    amendment=next(
        item for item in parse_architecture_amendments(text)
        if item.id==amendment_id
    )
    return {**baseline,"G1 redesign amendment":amendment.authority}


def resolve_launcher_paths(binding, owner):
    resolved=dict(binding)
    target=binding.get("target")
    if isinstance(target,str) and not target.startswith("-") and ("/" in target or target.startswith(".")):
        target_path=Path(target)
        if not target_path.is_absolute():
            target_path=owner.parent/target_path
        target_path=target_path.resolve()
        if not target_path.exists():
            raise RunnerError(f"launcher target path does not exist: {target}")
        resolved["target"]=str(target_path)
    arguments=binding.get("arguments")
    if not isinstance(arguments,list):
        return resolved
    normalized=[]
    for argument in arguments:
        path_like=isinstance(argument,str) and not argument.startswith("-") and ("/" in argument or argument.startswith("."))
        if not path_like:
            normalized.append(argument)
            continue
        candidate=Path(argument)
        if not candidate.is_absolute():
            candidate=owner.parent/candidate
        candidate=candidate.resolve()
        if not candidate.exists():
            raise RunnerError(f"launcher argument path does not exist: {argument}")
        normalized.append(str(candidate))
    resolved["arguments"]=normalized
    return resolved

def resolve_command_cwd(procedure, *, workspace_root, task_adapter, implementation_adapter):
    raw=procedure.get("commandCwd") if isinstance(procedure,dict) else None
    if raw in (None, "workspace"):
        path=workspace_root
    elif raw == "implementation-repository":
        path=implementation_adapter.parent.parent
    elif isinstance(raw,str) and raw.strip():
        path=(task_adapter.parent/raw).resolve()
    else:
        raise RunnerError("architecture procedure commandCwd must be workspace, implementation-repository, or an adapter-relative directory")
    path=path.resolve()
    if not path.is_dir() or not path.is_relative_to(workspace_root.resolve()):
        raise RunnerError(f"architecture launcher cwd must be an existing directory inside the workspace: {path}")
    return path

def launch(binding, prompt, session, cwd, required=(), *, usage_sink=None, usage_context=None, transcript_sink=None):
    if binding.get("kind")!="command" or binding.get("promptTransport")!="final-argument": raise RunnerError("architecture launchers must be command/final-argument")
    target,args=binding.get("target"),binding.get("arguments")
    if not isinstance(target,str) or not isinstance(args,list) or not all(isinstance(v,str) for v in args): raise RunnerError("invalid architecture launcher")
    environment=os.environ.copy()
    environment["ACDD_CODEX_WORKSPACE"]=str(cwd.resolve())
    try:
        run=subprocess.run([target,*(v.replace("{sessionUuid}",session) for v in args),prompt],cwd=cwd,env=environment,text=True,capture_output=True,check=False,timeout=LAUNCH_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        stdout=_text(exc.stdout); stderr=_text(exc.stderr)
        usage=parse_launcher_usage(stdout+"\n"+stderr)
        context={**(usage_context or {}),"sessionUuid":session}
        if usage_sink is not None:
            usage_sink.append({**context,**usage})
        if transcript_sink is not None:
            transcript_sink({"recordedAt":utc(),**context,"returnCode":None,"stdout":_bounded_text(stdout),"stderr":_bounded_text(stderr),"usage":usage})
        raise RunnerError(f"launcher timed out after {LAUNCH_TIMEOUT_SECONDS}s",retry_payload=_bounded_text(stderr or stdout,4096)) from exc
    stdout=_text(run.stdout); stderr=_text(run.stderr)
    usage=parse_launcher_usage(stdout+"\n"+stderr)
    context={**(usage_context or {}),"sessionUuid":session}
    if usage_sink is not None:
        usage_sink.append({**context,**usage})
    if transcript_sink is not None:
        transcript_sink({
            "recordedAt":utc(),
            **context,
            "returnCode":run.returncode,
            "stdout":_bounded_text(stdout),
            "stderr":_bounded_text(stderr),
            "usage":usage,
        })
    if _output_too_large(stdout,stderr):
        raise RunnerError(
            f"launcher output exceeded {MAX_LAUNCH_OUTPUT_BYTES} bytes",
            retry_payload={"stdout":_bounded_text(stdout,4096),"stderr":_bounded_text(stderr,4096)},
        )
    if run.returncode:
        transport_error=launcher_transport_error([
            value for stream in (stdout,stderr) for line in stream.splitlines()
            if (value:=decode_launcher_event(line)) is not None
        ])
        message=f"launcher transport failure: {transport_error}" if transport_error else f"launcher failed with exit code {run.returncode}"
        raise RunnerError(message,retry_payload=(stderr or stdout)[-4096:])
    try: return parse_launcher_output(stdout,required)
    except RunnerError as exc: raise RunnerError(str(exc),retry_payload=stdout[-4096:]) from exc
def check_partition(value, ident, fingerprint, schema, expected_value_domain_ids=frozenset(), expected_document=None, review_context=None):
    expected_task_paths = None
    expected_coverage_paths = None
    expected_repository_root = None
    if expected_document is not None:
        expected_task_paths = {expected_document.resolve().as_posix(), expected_document.name}
    if review_context:
        path_contract = review_context.get("pathContract")
        if isinstance(path_contract, dict):
            workspace_root = path_contract.get("workspaceRoot")
            if isinstance(workspace_root, str):
                try:
                    expected_task_paths = {
                        *(expected_task_paths or set()),
                        expected_document.resolve().relative_to(Path(workspace_root).resolve()).as_posix(),
                    }
                except (ValueError, AttributeError):
                    pass
            implementation_root = path_contract.get("implementationRepositoryRoot")
            expected_repository_root = (
                str(implementation_root)
                if isinstance(implementation_root, str)
                else (str(workspace_root) if isinstance(workspace_root, str) else None)
            )
        coverage = review_context.get("coverageFiles")
        if isinstance(coverage, list):
            expected_coverage_paths = {
                path
                for item in coverage
                if isinstance(item, dict)
                for path in (item.get("path"), item.get("repositoryPath"))
                if isinstance(path, str) and path.strip()
            }
    try:
        validate_partition_output(
            value,
            schema,
            label=f"partition {ident}",
            expected_id=ident,
            expected_fingerprint=fingerprint,
            expected_value_domain_ids=expected_value_domain_ids,
            expected_document=expected_document,
            expected_task_paths=expected_task_paths,
            expected_coverage_paths=expected_coverage_paths,
            expected_repository_root=expected_repository_root,
        )
    except ArchitectureVerificationError as exc:
        raise RunnerError(str(exc)) from exc
    if review_context:
        receipt=value.get("contextReceipt")
        if not isinstance(receipt,dict):
            raise RunnerError(f"partition {ident}.contextReceipt is required")
        if receipt.get("manifestSha256")!=review_context.get("sha256"):
            raise RunnerError(f"partition {ident}.contextReceipt manifest mismatch")
        consumption=review_context.get("consumptionContract",{})
        expected_sources=set(
            consumption.get("requiredSources",[])
            if isinstance(consumption,dict)
            else []
        )
        actual_sources=receipt.get("sourcesRead")
        if not isinstance(actual_sources,list) or set(actual_sources)!=expected_sources:
            raise RunnerError(f"partition {ident}.contextReceipt sourcesRead must exactly match the consumption contract")
        expected_retrievals=set(
            consumption.get("requiredRetrievals",[])
            if isinstance(consumption,dict)
            else []
        )
        actual_retrievals=receipt.get("retrievals")
        if not isinstance(actual_retrievals,list) or set(actual_retrievals)!=expected_retrievals:
            raise RunnerError(f"partition {ident}.contextReceipt misses required retrievals or contains unexpected retrievals")

def run_inspector(name,spec,fingerprint,document,root,launcher,schema,expected_value_domain_ids,max_attempts=2,usage_sink=None,review_subject=None,transcript_sink=None,review_context=None,command_cwd=None,discovery_root=None):
    last_error=None; prior_failure=None
    partition_fields=tuple(schema["partitionRequiredFields"])
    for attempt in range(1,max_attempts+1):
        session=str(uuid4()); value=None
        log(f"inspector:{name}: start attempt={attempt}/{max_attempts} session={session}")
        finding_shape={"id":"stable-id","defectKind":"missing-requirement|contradiction|infeasible-boundary|incomplete-propagation|unprovable-acceptance","candidateDefect":"defect in the frozen task design, not unfinished code","taskEvidence":["bound-task.md:line"],"codeEvidence":["services/or/packages/or/core/or/extensions/path:line"],"requiredTaskChange":"architecturally complete task-authority change"}
        subject=review_subject or {"kind":"pre-implementation architecture candidate","taskIsAuthority":True,"codeIsReadOnlyBaseline":True,"implementationCompletionIsOutOfScope":True}
        consumption=(review_context or {}).get("consumptionContract",{})
        context_receipt_contract={
            "manifestSha256":(review_context or {}).get("sha256"),
            "sourcesRead":list(
                consumption.get("requiredSources",[])
                if isinstance(consumption,dict)
                else []
            ),
            "retrievals":list(
                consumption.get("requiredRetrievals",[])
                if isinstance(consumption,dict)
                else []
            ),
        }
        discovery_contract={
            "repositoryRoot":str(discovery_root or root),
            "methods":{
                method:{
                    "capability":capability,
                    "tools":["successful tool name"],
                    "queries":["successful bounded query"],
                    "complete":True,
                }
                for method,capability in DISCOVERY_CAPABILITIES.items()
            },
        }
        output_contract={
            "topLevelKeys":[
                *schema["partitionRequiredFields"],
                *(["contextReceipt"] if review_context else []),
            ],
            "id":name,
            "status":"pass|fail",
            "inputFingerprint":fingerprint,
            "evidence":["path:line"],
            "findings":[finding_shape],
            "discovery":discovery_contract,
            "persistedContractMappings":"allowed domain IDs only",
            "isolated":True,
            "readOnly":True,
        }
        if review_context:
            output_contract["contextReceipt"]=context_receipt_contract
        coverage_policy=(
            "Use only reviewContext.coverageFiles as this admission's frozen code coverage. "
            "For workspace-rooted tools use each entry's path. For implementation-repository-rooted "
            "tools use repositoryPath exactly; never prepend the implementation repository directory. "
            "Treat coverageSelectors as scope explanation, not permission to widen into another G0 or G1 admission."
            if (review_context or {}).get("pathContract")
            else
            "Use only the supplied reviewContext coverage as this admission's frozen code coverage; "
            "do not widen into another G0 or G1 admission."
        )
        context_instruction=(
            "The reviewContext manifest, its gate-scoped coverageFiles, pathContract, and declared authority sources are mandatory review inputs. "
            "Return contextReceipt exactly matching contextReceiptContract to prove the bound manifest, authority sources, and retrieval operations were consumed. "
            if review_context
            else ""
        )
        tool_policy={
            "coverage":coverage_policy,
            "discoveryReceipts":"Record only successful tool calls. A rejected or failed call does not satisfy a discovery method; correct the invocation and complete a successful bounded call before returning complete=true.",
            **(
                (review_context or {}).get("toolPolicy",{})
                if isinstance((review_context or {}).get("toolPolicy"),dict)
                else {}
            ),
        }
        prompt=json.dumps({"inputFingerprint":fingerprint,"document":str(document),"workspaceRoot":str(root),"partition":spec,"sessionUuid":session,"priorAttemptFailure":prior_failure,"reviewSubject":subject,"reviewContext":review_context or {},"contextReceiptContract":context_receipt_contract if review_context else None,"discoveryContract":discovery_contract,"outputContract":output_contract,"persistedContractContract":{"allowedDomainIds":sorted(expected_value_domain_ids),"coverage":"complete" if name in {"contract","persistence"} else "relevant-subset","forbiddenIdKinds":["proof","matrix"]},"findingContract":{"shape":finding_shape,"rule":"A finding is valid only when the frozen architecture authority omits, contradicts, makes infeasible, incompletely propagates, or cannot prove an architectural requirement. Current code is read-only evidence and is never by itself a finding. If the authority already specifies the canonical owner, required end state, propagation, prohibited behavior, and acceptance proof, do not fail on presentation shape."},"toolPolicy":tool_policy,"instruction":"Review the frozen architecture authority against the read-only current code. "+context_instruction+"Return exactly one JSON object matching outputContract byte-for-shape: no markdown, no extra keys, no omitted keys. For an amendment, judge only that amendment's coverage and decisions and their coherence with the frozen G0 baseline; do not reuse another amendment's coverage or reopen unrelated G0 decisions. findings is an array of objects exactly matching findingContract.shape; fail requires at least one authority defect and pass requires findings=[]. Every evidence, taskEvidence, and codeEvidence item is one path:line string; ranges and objects are forbidden. taskEvidence must cite the bound task; other authority context belongs in evidence. codeEvidence must cite repository code inside this admission's coverage or explain a coverage omission as a task defect. persistedContractMappings contains only allowed domain IDs. discovery must exactly match discoveryContract and may name only successful calls. Preserve substantive prior FAIL content only if it satisfies this candidate-defect contract."})
        try:
            value=launch(launcher,prompt,session,command_cwd or root,partition_fields,usage_sink=usage_sink,usage_context={"role":"inspector","partition":name,"attempt":attempt},transcript_sink=transcript_sink)
            check_partition(value,name,fingerprint,schema,expected_value_domain_ids,document,review_context)
            log(f"inspector:{name}: finish status={value['status']} attempt={attempt}")
            return value
        except RunnerError as exc:
            last_error=exc
            retry_payload=exc.retry_payload if exc.retry_payload is not None else value
            prior_failure={"validationError":str(exc),"responseExcerpt":json.dumps(retry_payload,ensure_ascii=False,default=str)[:8192]}
            log(f"inspector:{name}: transport/schema failure attempt={attempt}: {exc}")
    raise RunnerError(f"inspector {name} exhausted {max_attempts} transport/schema attempts: {last_error}",retry_payload=prior_failure)

def task_findings_from_recommendations(recommendations):
    return [
        {
            "id":item["id"],
            "partition":"coordinator",
            "summary":item["requiredChange"],
            "invariant":item["invariant"],
            "rootCause":item["rootCause"],
            "canonicalOwner":item["canonicalOwner"],
            "propagation":item["propagation"],
            "prohibitedShortcuts":item["prohibitedShortcuts"],
            "acceptanceProof":item["acceptanceProof"],
            "sourceFindings":item["sourceFindings"],
            "evidence":item["evidence"],
            "userDecisionRequired":item.get("userDecisionRequired",False),
            "decisionOptions":item.get("decisionOptions",[]),
        }
        for item in recommendations
    ]


def unreconciled_partition_findings(partitions):
    return [
        {
            "id":f"{item['id']}:{index}",
            "partition":item["id"],
            "summary":str(finding.get("candidateDefect",finding)).replace("\n"," ")[:1024] if isinstance(finding,dict) else str(finding).replace("\n"," ")[:1024],
            "finding":finding,
            "status":"unreconciled",
            "evidence":item["evidence"][:8],
        }
        for item in partitions
        for index,finding in enumerate(item["findings"],1)
    ]


def schema_failed_partition_findings(name, error):
    validation_error=str(error).replace("\n"," ")[:1024]
    payload=json.dumps(error.retry_payload,ensure_ascii=False,default=str)
    raw_response,_=redact_secrets(payload[-4096:])
    raw_findings=[]
    try:
        candidate=parse_launcher_output(payload,("findings",))
        if isinstance(candidate.get("findings"),list):
            raw_findings=[item for item in candidate["findings"] if (isinstance(item,str) and item.strip()) or isinstance(item,dict)]
    except RunnerError:
        pass
    if not raw_findings:
        return [{"id":f"{name}:schema","partition":name,"summary":validation_error,"status":"schema-blocked","validationError":validation_error,"rawResponse":raw_response,"containsFail":"FAIL" in raw_response.upper(),"evidence":[]}]
    return [
        {"id":f"{name}:schema:{index}","partition":name,"summary":str(finding.get("candidateDefect",finding) if isinstance(finding,dict) else finding).replace("\n"," ")[:1024],"finding":finding,"status":"unreconciled-schema","validationError":validation_error,"rawResponse":raw_response,"containsFail":"FAIL" in raw_response.upper(),"evidence":[]}
        for index,finding in enumerate(raw_findings,1)
    ]


def collect_inspector_wave(names,run_one,maximum):
    outputs={}; failures={}
    with concurrent.futures.ThreadPoolExecutor(max_workers=maximum) as pool:
        futures={pool.submit(run_one,name):name for name in names}
        for future in concurrent.futures.as_completed(futures):
            name=futures[future]
            try:
                outputs[name]=future.result()
            except RunnerError as exc:
                failures[name]=exc
            except Exception as exc:
                failures[name]=RunnerError(f"unexpected inspector failure: {exc}")
    partitions=[outputs[name] for name in names if name in outputs]
    if failures:
        findings=unreconciled_partition_findings(partitions)
        for name in names:
            if name in failures:
                findings.extend(schema_failed_partition_findings(name,failures[name]))
        summary="; ".join(f"{name}: {failures[name]}" for name in names if name in failures)
        raise RunnerError(
            "inspector wave blocked after all partitions terminated: "+summary,
            retry_payload={name:failures[name].retry_payload for name in names if name in failures},
            findings=findings,
            partitions=partitions,
        )
    return [outputs[name] for name in names]


def run_coordinator(partitions,fingerprint,launcher,root,procedure,schema,contract,expected_persisted_contract_ids,max_attempts=2,candidate_authority=None,usage_sink=None,transcript_sink=None,review_context=None,expected_document=None,command_cwd=None):
    source_findings=[
        {"ref":f"{item['id']}:{index}","partition":item["id"],"finding":finding,"evidence":item["evidence"]}
        for item in partitions
        for index,finding in enumerate(item["findings"],1)
    ]
    recommendation_fields=["id","sourceFindings","invariant","rootCause","canonicalOwner","requiredChange","propagation","prohibitedShortcuts","acceptanceProof","evidence","userDecisionRequired","decisionOptions"]
    recommendation_shape={
        "id":"stable-id",
        "sourceFindings":["contract:1"],
        "invariant":"non-empty string",
        "rootCause":"non-empty string",
        "canonicalOwner":"non-empty string",
        "requiredChange":"non-empty string",
        "propagation":["caller -> canonical owner","transport/storage/backend propagation"],
        "prohibitedShortcuts":["symptom-level workaround to reject"],
        "acceptanceProof":["proof that closes the invariant"],
        "evidence":["path:line"],
        "userDecisionRequired":False,
        "decisionOptions":[],
    }
    prior_failure=None; last_error=None
    for attempt in range(1,max_attempts+1):
        coordinator=str(uuid4()); raw_result=None
        log(f"coordinator: start attempt={attempt}/{max_attempts} session={coordinator} source-findings={len(source_findings)}")
        prompt=json.dumps({"inputFingerprint":fingerprint,"candidateAuthority":candidate_authority or {},"reviewContext":review_context or {},"partitions":partitions,"sourceFindings":source_findings,"priorAttemptFailure":prior_failure,"outputContract":{"topLevelRequired":["coordinator"],"coordinatorRequired":["verdict","resolvedFindings","reconciledRecommendations"],"recommendationRequired":recommendation_fields,"recommendationShape":recommendation_shape},"recommendationPolicy":{"goal":"Reconcile only genuine defects in the frozen task architecture candidate.","resolution":"Put a source ref in resolvedFindings when its required architectural state is already fully and unambiguously specified by candidateAuthority. Current legacy or not-yet-implemented code is not a candidate defect.","requirements":["State the violated invariant and root cause.","Name the canonical owner boundary where the invariant must be fixed.","Describe the required task end state, not product-code completion or code snippets.","Cover every affected caller, transport, storage path, backend, compatibility surface, and lifecycle transition.","Name prohibited symptom-level shortcuts.","Specify acceptance proof.","When a serious contradiction or architectural gap has multiple materially different valid interpretations, set userDecisionRequired=true. Provide both update-task:<decision needed> and create-linked-plan:<scope to extract and link> options; do not silently choose one."],"coverage":"Every sourceFindings ref must occur exactly once in resolvedFindings or across reconciledRecommendations.sourceFindings."},"instruction":"Use only candidateAuthority, reviewContext, validated partitions, and sourceFindings; do not search or call tools. Independently test every finding against the frozen task authority. Resolve findings that merely observe unfinished/legacy implementation or restate requirements already complete in the task. Return exactly one JSON object whose only top-level key is coordinator and whose coordinator has exactly verdict, resolvedFindings, and reconciledRecommendations. PASS requires every source finding resolved and no recommendations. FAIL requires at least one architecturally complete recommendation. Never require product implementation before G0. Mark interpretation-dependent serious contradictions/gaps for explicit user validation; never rewrite task authority or invent a plan decision. Do not emit markdown or extra keys."})
        try:
            raw_result=launch(launcher,prompt,coordinator,command_cwd or root,("coordinator",),usage_sink=usage_sink,usage_context={"role":"coordinator","partition":"coordinator","attempt":attempt},transcript_sink=transcript_sink)
            if set(raw_result)!={"coordinator"} or not isinstance(raw_result["coordinator"],dict):
                raise RunnerError("coordinator must return only one coordinator object")
            model_result=raw_result["coordinator"]
            if set(model_result)!={"verdict","resolvedFindings","reconciledRecommendations"}:
                raise RunnerError("coordinator model output must contain verdict, resolvedFindings, and reconciledRecommendations only")
            result={"inputFingerprint":fingerprint,"runtime":str(procedure["runtime"]),"capabilities":list(schema["requiredCapabilities"]),"isolated":True,"readOnly":True,"authoritativeSessionUuids":[coordinator],"persistedContractIds":sorted(expected_persisted_contract_ids),"partitions":partitions,"coordinator":{"sessionUuid":coordinator,"verdict":model_result["verdict"],"findingsReconciled":True,"persistedContractsReconciled":True,"resolvedFindings":model_result["resolvedFindings"],"reconciledRecommendations":model_result["reconciledRecommendations"]},"usage":summarize_usage(usage_sink or []),"reviewContext":review_context or {}}
            coverage_paths = None
            expected_repository_root = None
            expected_task_paths = None
            if expected_document is not None:
                expected_task_paths={expected_document.resolve().as_posix(),expected_document.name}
            if isinstance(review_context, dict):
                coverage = review_context.get("coverageFiles")
                if isinstance(coverage, list):
                    coverage_paths = {
                        path
                        for item in coverage
                        if isinstance(item, dict)
                        for path in (item.get("path"), item.get("repositoryPath"))
                        if isinstance(path, str) and path.strip()
                    }
                path_contract = review_context.get("pathContract")
                if isinstance(path_contract, dict):
                    expected_repository_root = path_contract.get(
                        "implementationRepositoryRoot",
                        path_contract.get("workspaceRoot"),
                    )
                    try:
                        expected_task_paths.add(expected_document.resolve().relative_to(Path(expected_repository_root).resolve()).as_posix())
                    except (ValueError, AttributeError):
                        pass
            validate_result(
                contract,
                schema,
                result,
                expected_value_domain_ids=expected_persisted_contract_ids,
                expected_document=expected_document,
                expected_task_paths=expected_task_paths,
                expected_repository_root=expected_repository_root,
                expected_coverage_paths=coverage_paths,
            )
            log(f"coordinator: finish verdict={result['coordinator']['verdict']} attempt={attempt}")
            return result
        except (RunnerError,ArchitectureVerificationError) as exc:
            last_error=exc
            retry_payload=exc.retry_payload if isinstance(exc,RunnerError) and exc.retry_payload is not None else raw_result
            prior_failure={"validationError":str(exc),"responseExcerpt":json.dumps(retry_payload,ensure_ascii=False,default=str)[:16384]}
            log(f"coordinator: transport/schema failure attempt={attempt}: {exc}")
    coordinator_error = last_error if isinstance(last_error, RunnerError) else RunnerError(
        str(last_error), retry_payload=prior_failure
    )
    findings = unreconciled_partition_findings(partitions)
    findings.extend(schema_failed_partition_findings("coordinator", coordinator_error))
    raise RunnerError(
        f"coordinator exhausted {max_attempts} transport/schema attempts: {last_error}",
        retry_payload=prior_failure,
        findings=findings,
        partitions=partitions,
    )


def replace_section(text,title,body):
    marker="## "+title
    if marker not in text: return text.rstrip()+"\n\n"+marker+"\n\n"+body.rstrip()+"\n"
    return re.sub(r"(?ms)^"+re.escape(marker)+r"\n.*?(?=^## |\Z)",marker+"\n\n"+body.rstrip()+"\n\n",text)
def record_attempt(document,fingerprint,verdict,coordinator,partitions,findings,usage=None,review_context=None):
    text=document.read_text(encoding="utf-8"); prior=parse_architecture_admission(text)
    section=markdown_sections(text).get("ACDD architecture admission","").strip()
    payload=None
    if section.startswith(fence()+"yaml\n") and section.endswith("\n"+fence()):
        payload=yaml.safe_load(section[len(fence()+"yaml\n"):-len("\n"+fence())])
    if not isinstance(payload,dict):
        payload={"apiVersion":"acdd/architecture-admission/v1","kind":"architecture-admission","maxMaterialAttempts":prior.max_material_attempts,"candidateSet":[{"path":x.path,"sha256":x.sha256} for x in prior.candidate_set],"attempts":[]}
    attempts=payload.get("attempts")
    if not isinstance(attempts,list): attempts=[]
    entry={"inputFingerprint":fingerprint,"verdict":verdict,"recordedAt":utc()}
    if coordinator: entry["coordinatorSession"]=coordinator
    if partitions: entry["partitionStatuses"]={x["id"]:x["status"] for x in partitions}
    if findings: entry["findings"]=findings
    if usage is not None: entry["usage"]=usage
    if review_context:
        entry["reviewContext"]={
            key:review_context[key]
            for key in ("path","sha256")
            if key in review_context
        }
    attempts.append(entry)
    payload["attempts"]=attempts
    document.write_text(replace_section(text,"ACDD architecture admission",fence()+"yaml\n"+yaml.safe_dump(payload,sort_keys=False).rstrip()+"\n"+fence()),encoding="utf-8")
def add_pass(document,fingerprint,adapter,author,result,semantic_fingerprint=None,code_fingerprint=None):
    text=document.read_text(encoding="utf-8"); evidence_id="architecture.runner."+fingerprint.split(":",1)[1][:12]
    review={"apiVersion":"acdd/gate-evidence/v1","kind":"review","id":evidence_id,"gate":"architecture/v1","inputFingerprint":fingerprint,"adapter":adapter,"sessionUuid":result["coordinator"]["sessionUuid"],"authorSessionUuid":author,"reviewer":"acdd architecture runner","independent":True,"terminalVerdict":"PASS","authoritySources":[document.name],"productionPaths":["four independent partitions"],"directCallers":["partition:callers"],"alternateCallers":["partition:authority"],"contradictions":[],"impactAxes":{"architecture":"reviewed"},"matrixMappings":["partition:contract"],"proofMappings":["partition:persistence"],"findings":[],"inventoryComplete":True,"decisionsResolved":True,"callerCoverageComplete":True,"persistedContractChange":bool(result["persistedContractIds"]),"persistedContractMappings":list(result["persistedContractIds"]),"discoveryComplete":True,"verification":result}
    if semantic_fingerprint is not None:
        review["baseG0Fingerprint"]=semantic_fingerprint
    if code_fingerprint is not None:
        review["codeSnapshotFingerprint"]=code_fingerprint
    old=markdown_sections(text).get("ACDD gate evidence","").strip(); dumped=yaml.safe_dump(review,sort_keys=False).rstrip(); opening=fence()+"yaml\n"; closing="\n"+fence()
    if old==opening+"[]"+closing: body=opening+dumped+closing
    elif old.startswith(opening) and old.endswith(closing): body=old[:-len(fence())]+"\n---\n"+dumped+closing
    else: raise RunnerError("gate evidence must be a YAML fence")
    text=replace_section(text,"ACDD gate evidence",body)
    mark=chr(96); row="| "+mark+"architecture/v1"+mark+" | "+mark+"pass"+mark+" | evidence="+evidence_id+" | "+mark+fingerprint+mark+" | "+mark+utc()+mark+" |"
    text=re.sub(r"(?m)^\| "+re.escape(mark)+r"architecture/v1"+re.escape(mark)+r" \|.*$",row,text)
    document.write_text(text,encoding="utf-8")


def artifact_recorder_path(root,task_adapter,adapter,required=True):
    scripts=adapter.get("scripts")
    raw=scripts.get("architectureArtifacts") if isinstance(scripts,dict) else None
    if not isinstance(raw,str) or not raw.strip():
        if required:
            raise RunnerError("task adapter must declare scripts.architectureArtifacts")
        return None
    path=(task_adapter.parent/raw).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise RunnerError("task adapter scripts.architectureArtifacts is missing or escapes the workspace")
    return path


def call_artifact_recorder(script,operation,root,document,amendment_id,payload):
    command=[
        sys.executable,
        str(script),
        operation,
        "--workspace-root",
        str(root),
        "--document",
        str(document),
    ]
    if amendment_id is not None:
        command.extend(["--amendment",amendment_id])
    run=subprocess.run(
        command,
        cwd=root,
        text=True,
        input=json.dumps(payload,ensure_ascii=False),
        capture_output=True,
        check=False,
    )
    if run.returncode:
        detail=(run.stderr or run.stdout).strip().replace("\n"," ")[:1024]
        raise RunnerError(f"architecture artifact recorder {operation} failed: {detail}")
    if not run.stdout.strip():
        return {}
    try:
        result=json.loads(run.stdout)
    except json.JSONDecodeError as exc:
        raise RunnerError(f"architecture artifact recorder {operation} returned invalid JSON") from exc
    if not isinstance(result,dict):
        raise RunnerError(f"architecture artifact recorder {operation} must return one JSON object")
    return result
def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document",type=Path,required=True)
    parser.add_argument("--workspace-root",type=Path,required=True)
    parser.add_argument("--profile",type=Path,required=True)
    parser.add_argument("--receipt-contract",type=Path,required=True)
    parser.add_argument("--adapter",action="append",required=True)
    parser.add_argument(
        "--amendment",
        help="Review one G1 redesign amendment without replacing the G0 receipt",
    )
    check_group=parser.add_mutually_exclusive_group(required=True)
    check_group.add_argument("--check-command")
    check_group.add_argument("--check-arg",action="append",dest="check_args")
    parser.add_argument("--author-session",default=str(uuid4()))
    args=parser.parse_args(argv)
    root=args.workspace_root.resolve(); document=args.document.resolve(); fingerprint=None; usage_records=[]
    artifact_script=None; artifact_sink=None; amendment_launch_admitted=False; amendment_attempt_recorded=False; invocation_uuid=str(uuid4())
    try:
        sections=markdown_sections(document.read_text(encoding="utf-8"))
        if "ACDD contract changes" in sections:
            log("fingerprint: preserving historical baseline for declared contract change")
        else:
            log("fingerprint: recording current semantic fingerprint")
            subprocess.run([sys.executable,str(Path(__file__).with_name("record_fingerprint.py")),"--document",str(document),"--write"],cwd=root,check=True)
        log("preflight: running bound-task drift, contract, shape, and admission checks")
        if args.check_args is not None:
            check_command=list(args.check_args)
            if args.amendment:
                check_command.extend(
                    ["--reviewing-amendment",args.amendment]
                )
            check_run=subprocess.run(check_command,cwd=root,check=False)
        else:
            check_run=subprocess.run(args.check_command,cwd=root,shell=True,check=False)
        if check_run.returncode:
            raise RunnerError("check failed before architecture launch")
        log("preflight: PASS")

        core,adapters=load_core(args.profile.resolve()),_adapter_args(args.adapter)
        task_adapter=adapters["task"].resolve()
        adapter=load_adapter(task_adapter,"task",core,allowed_root=root)
        artifact_script=artifact_recorder_path(
            root,task_adapter,adapter,required=args.amendment is not None
        )
        procedure=adapter["gateProcedures"]["architecture/v1"]
        launchers=procedure.get("launchers") if isinstance(procedure,dict) else None
        if isinstance(launchers,dict):
            launchers_mode="split"
        else:
            legacy_launcher=procedure.get("launcher") if isinstance(procedure,dict) else None
            if not isinstance(legacy_launcher,dict):
                raise RunnerError("runner requires launcher or split launchers")
            launchers={"inspector":legacy_launcher,"coordinator":legacy_launcher}
            launchers_mode="legacy"
        launchers={name:resolve_launcher_paths(binding,task_adapter) for name,binding in launchers.items()}
        command_cwd=resolve_command_cwd(
            procedure,
            workspace_root=root,
            task_adapter=task_adapter,
            implementation_adapter=adapters["implementation"].resolve(),
        )
        log(f"launchers: command cwd={command_cwd}")
        contract=load_yaml((task_adapter.parent/procedure["contract"]).resolve())
        schema=core.architecture_verification_schema
        if schema is None: raise RunnerError("task profile has no architecture schema")
        validate_contract(contract,schema)
        inspectors={item["id"]:item for item in contract["inspectors"]}
        maximum=int(schema["maxParallelInspectors"])
        if len(inspectors)!=4 or maximum!=4: raise RunnerError("architecture/v1 requires exactly four inspectors")
        log("contract: loaded four partitions: "+", ".join(inspectors))

        adapter_paths=tuple(path.resolve() for path in adapters.values())
        if args.amendment:
            amendments=parse_architecture_amendments(
                document.read_text(encoding="utf-8")
            )
            amendment=next(
                (item for item in amendments if item.id==args.amendment),
                None,
            )
            if amendment is None:
                raise RunnerError(
                    f"unknown architecture amendment {args.amendment!r}"
                )
            if amendment.review.get("status")=="pass":
                raise RunnerError(
                    f"architecture amendment {args.amendment!r} already passed"
                )
            fingerprint=architecture_amendment_fingerprint(
                document.read_text(encoding="utf-8"),args.amendment
            )
            coverage_scope={"gate":"G1","id":args.amendment}
            coverage_selectors=tuple(
                str(item) for item in amendment.authority["implementationPaths"]
            )
            coverage_entries=architecture_code_snapshot_entries(
                document=document,
                adapters=adapter_paths,
                workspace_root=root,
                selectors=coverage_selectors,
            )
            code_snapshot=fingerprint_architecture_code_inputs(
                document=document,
                adapters=adapter_paths,
                workspace_root=root,
                selectors=coverage_selectors,
            ).sha256
            prepared=call_artifact_recorder(
                artifact_script,
                "prepare",
                root,
                document,
                args.amendment,
                {
                    "invocationUuid":invocation_uuid,
                    "inputFingerprint":fingerprint,
                    "baseG0Fingerprint":amendment.base_g0_fingerprint,
                    "codeSnapshotFingerprint":code_snapshot,
                },
            )
            raw_attempts=prepared.get("attempts",[])
            if not isinstance(raw_attempts,list):
                raise RunnerError("architecture artifact recorder prepare must return attempts")
            attempts=[
                ArchitectureAttempt(
                    str(item["inputFingerprint"]),
                    str(item["verdict"]).upper(),
                    str(item["recordedAt"]),
                )
                for item in raw_attempts
            ]
            validate_retry_admission(
                attempts,
                next_fingerprint=fingerprint,
            )
            log(
                "fingerprint: amendment="+fingerprint
                +" base-g0="+amendment.base_g0_fingerprint
                +" code-snapshot="+code_snapshot
            )
        else:
            coverage_scope={"gate":"G0","id":"g0"}
            coverage_selectors=()
            coverage_entries=architecture_code_snapshot_entries(
                document=document,
                adapters=adapter_paths,
                workspace_root=root,
            )
            candidate=fingerprint_architecture_candidate(
                document=document,
                adapters=adapter_paths,
                workspace_root=root,
            )
            fingerprint=candidate.sha256
            code_snapshot=candidate.code_sha256
            log(
                "fingerprint: candidate="+fingerprint
                +" semantic="+candidate.semantic_sha256
                +" code="+candidate.code_sha256
            )
        review_context={}
        if artifact_script is not None:
            context_result=call_artifact_recorder(
                artifact_script,
                "context",
                root,
                document,
                args.amendment,
                {
                    "invocationUuid":invocation_uuid,
                    "inputFingerprint":fingerprint,
                    "baseG0Fingerprint":(
                        amendment.base_g0_fingerprint
                        if args.amendment
                        else candidate.semantic_sha256
                    ),
                    "declaredInputs":[
                        item.path
                        for item in parse_inputs(
                            document.read_text(encoding="utf-8")
                        )
                    ],
                    "coverageScope":coverage_scope,
                    "coverageSelectors":list(coverage_selectors),
                    "coverageFiles":[
                        {
                            "type":entry.type,
                            "path":entry.path,
                            "sha256":entry.sha256,
                        }
                        for entry in coverage_entries
                    ],
                    "codeSnapshotFingerprint":code_snapshot,
                },
            )
            raw_context=context_result.get("context")
            if not isinstance(raw_context,dict):
                raise RunnerError(
                    "architecture artifact recorder context must return one context manifest"
                )
            review_context=raw_context
            log(
                "context: manifest="
                +str(review_context.get("path","missing"))
                +" sources="
                +str(len(review_context.get("sources",[])))
            )
        text=document.read_text(encoding="utf-8")
        expected_persisted_contract_ids=frozenset(
            domain.id
            for domain in parse_value_domains(
                text,
                workspace_root=root,
                declared_paths=frozenset(item.path for item in parse_inputs(text)),
                semantic_ids=frozenset(architecture_authority_ids(text)),
            )
        )
        if args.amendment:
            amendment_launch_admitted=True
            artifact_sink=lambda record:call_artifact_recorder(
                artifact_script,
                "launch",
                root,
                document,
                args.amendment,
                {
                    "invocationUuid":invocation_uuid,
                    "inputFingerprint":fingerprint,
                    "record":record,
                },
            )
        else:
            validate_architecture_admission(text=text,workspace_root=root,architecture_fingerprint=fingerprint)
        log(f"admission: PASS fingerprint={fingerprint}")
        def run_one(name):
            return run_inspector(
                name,
                inspectors[name],
                fingerprint,
                document,
                root,
                launchers["inspector"],
                schema,
                expected_persisted_contract_ids,
                usage_sink=usage_records,
                transcript_sink=artifact_sink,
                review_context=review_context,
                review_subject=(
                    {
                        "kind":"G1 architecture amendment",
                        "amendmentId":args.amendment,
                        "baseG0Fingerprint":amendment.base_g0_fingerprint,
                        "taskIsAuthority":True,
                        "codeIsReadOnlyImplementationEvidence":True,
                        "scope":"amendment decisions and coherence with frozen G0 only",
                    }
                    if args.amendment
                    else None
                ),
                command_cwd=command_cwd,
                discovery_root=command_cwd,
            )

        log(f"inspectors: launching one parallel wave of four adapter processes ({launchers_mode} launcher mode)")
        partitions=collect_inspector_wave(tuple(inspectors),run_one,maximum)
        log("inspectors: all four outputs validated")

        result=run_coordinator(
            partitions,
            fingerprint,
            launchers["coordinator"],
            root,
            procedure,
            schema,
            contract,
            expected_persisted_contract_ids,
            candidate_authority=semantic_candidate_authority(text,args.amendment),
            usage_sink=usage_records,
            transcript_sink=artifact_sink,
            review_context=review_context,
            expected_document=document,
            command_cwd=command_cwd,
        )
        log("snapshot: rechecking frozen task and allowed code inputs")
        if args.amendment:
            current_fingerprint=architecture_amendment_fingerprint(
                document.read_text(encoding="utf-8"),args.amendment
            )
            current_code=fingerprint_architecture_code_inputs(
                document=document,
                adapters=adapter_paths,
                workspace_root=root,
                selectors=coverage_selectors,
            ).sha256
            unchanged=(
                current_fingerprint==fingerprint
                and current_code==code_snapshot
            )
        else:
            current_candidate=fingerprint_architecture_candidate(
                document=document,
                adapters=adapter_paths,
                workspace_root=root,
            )
            unchanged=current_candidate.sha256==fingerprint
        if not unchanged:
            raise RunnerError(
                "review inputs changed while verification ran",
                partitions=partitions,
            )
        log("snapshot: unchanged")
        coordinator=result["coordinator"]["sessionUuid"]
        findings=task_findings_from_recommendations(
            result["coordinator"]["reconciledRecommendations"]
        )
        verdict=result["coordinator"]["verdict"]
        log(f"terminal: recording verdict={verdict} findings={len(findings)}")
        if args.amendment:
            call_artifact_recorder(
                artifact_script,
                "terminal",
                root,
                document,
                args.amendment,
                {
                    "invocationUuid":invocation_uuid,
                    "inputFingerprint":fingerprint,
                    "baseG0Fingerprint":amendment.base_g0_fingerprint,
                    "codeSnapshotFingerprint":code_snapshot,
                    "verdict":verdict,
                    "coordinatorSession":coordinator,
                    "partitions":partitions,
                    "findings":findings,
                    "usage":summarize_usage(usage_records),
                    "verification":result,
                    "reviewContext":review_context,
                },
            )
            amendment_attempt_recorded=True
        else:
            record_attempt(document,fingerprint,verdict,coordinator,partitions,findings,summarize_usage(usage_records),review_context)
        if verdict=="PASS":
            if not args.amendment:
                add_pass(
                    document,
                    fingerprint,
                    adapter["id"],
                    args.author_session,
                    result,
                    candidate.semantic_sha256,
                    candidate.code_sha256,
                )
            log("terminal: PASS evidence and receipt written")
        return 0 if verdict=="PASS" else 1
    except (RunnerError,ArchitectureGovernorError,ArchitectureVerificationError,ContractError,subprocess.CalledProcessError,OSError,KeyError,TypeError,ValueError) as exc:
        log("blocked: "+str(exc))
        if fingerprint:
            try:
                blocked_findings=exc.findings if isinstance(exc,RunnerError) and exc.findings else [{"id":"runner","partition":"runner","summary":str(exc)[:512],"evidence":[]}]
                blocked_partitions=exc.partitions if isinstance(exc,RunnerError) else []
                if args.amendment:
                    if amendment_launch_admitted and not amendment_attempt_recorded:
                        call_artifact_recorder(
                            artifact_script,
                            "terminal",
                            root,
                            document,
                            args.amendment,
                            {
                                "invocationUuid":invocation_uuid,
                                "inputFingerprint":fingerprint,
                                "baseG0Fingerprint":amendment.base_g0_fingerprint,
                                "codeSnapshotFingerprint":code_snapshot,
                                "verdict":"BLOCKED",
                                "coordinatorSession":None,
                                "partitions":blocked_partitions,
                                "findings":blocked_findings,
                                "usage":summarize_usage(usage_records),
                                "verification":None,
                                "reviewContext":review_context,
                            },
                        )
                else:
                    record_attempt(document,fingerprint,"BLOCKED",None,blocked_partitions,blocked_findings,summarize_usage(usage_records),review_context)
            except Exception as record_error:
                log(f"blocked: failed to record terminal attempt: {record_error}")
        return 2
if __name__=="__main__": raise SystemExit(main())
