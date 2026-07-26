#!/usr/bin/env python3
"""Fail-closed concurrent architecture/v1 runner."""
from __future__ import annotations
import argparse, concurrent.futures, json, re, subprocess, sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
import yaml
from acdd_fingerprint import (
    TASK_OPTIONAL_SEMANTIC_SECTIONS,
    TASK_SEMANTIC_SECTIONS,
    fingerprint_architecture_candidate,
    markdown_sections,
    parse_inputs,
    semantic_task_fingerprint,
)
from architecture_governor import ArchitectureGovernorError, parse_architecture_admission, validate_architecture_admission
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
def utc(): return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00","Z")
def log(message): print(f"[architecture {utc()}] {message}",file=sys.stderr,flush=True)
def fence(): return chr(96) * 3
def parse_launcher_output(output, required=()):
    required_set=set(required); roots=[]
    def decode(text):
        value=text.strip()
        if value.startswith("```"):
            value=re.sub(r"^\`\`\`(?:json)?\s*|\s*\`\`\`$","",value,flags=re.I)
        try: return json.loads(value)
        except json.JSONDecodeError: return None
    whole=decode(output)
    if whole is not None: roots.append(whole)
    for block in re.findall(r"```(?:json)?\s*(.*?)```",output,flags=re.I|re.S):
        value=decode(block)
        if value is not None: roots.append(value)
    for line in output.splitlines():
        value=decode(line)
        if value is not None: roots.append(value)
    def candidates(value):
        if isinstance(value,dict):
            yield value
            for nested in value.values(): yield from candidates(nested)
        elif isinstance(value,list):
            for nested in value: yield from candidates(nested)
        elif isinstance(value,str) and value.strip().startswith(("{","[","```")):
            nested=decode(value)
            if nested is not None and nested != value: yield from candidates(nested)
    matches=[item for root_value in roots for item in candidates(root_value) if required_set<=set(item)]
    if not matches: raise RunnerError("launcher did not return the required JSON object")
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

def semantic_candidate_authority(text):
    sections=markdown_sections(text)
    return {
        name:sections[name].strip()
        for name in TASK_SEMANTIC_SECTIONS+TASK_OPTIONAL_SEMANTIC_SECTIONS
        if name in sections
    }

def launch(binding, prompt, session, cwd, required=(), *, usage_sink=None, usage_context=None):
    if binding.get("kind")!="command" or binding.get("promptTransport")!="final-argument": raise RunnerError("architecture launchers must be command/final-argument")
    target,args=binding.get("target"),binding.get("arguments")
    if not isinstance(target,str) or not isinstance(args,list) or not all(isinstance(v,str) for v in args): raise RunnerError("invalid architecture launcher")
    run=subprocess.run([target,*(v.replace("{sessionUuid}",session) for v in args),prompt],cwd=cwd,text=True,capture_output=True,check=False)
    usage=parse_launcher_usage(run.stdout)
    if usage_sink is not None:
        usage_sink.append({**(usage_context or {}),"sessionUuid":session,**usage})
    if run.returncode: raise RunnerError("launcher failed",retry_payload=(run.stderr or run.stdout)[-4096:])
    try: return parse_launcher_output(run.stdout,required)
    except RunnerError as exc: raise RunnerError(str(exc),retry_payload=run.stdout[-4096:]) from exc
def check_partition(value, ident, fingerprint, schema, expected_value_domain_ids=frozenset(), expected_document=None):
    try:
        validate_partition_output(
            value,
            schema,
            label=f"partition {ident}",
            expected_id=ident,
            expected_fingerprint=fingerprint,
            expected_value_domain_ids=expected_value_domain_ids,
            expected_document=expected_document,
        )
    except ArchitectureVerificationError as exc:
        raise RunnerError(str(exc)) from exc

def run_inspector(name,spec,fingerprint,document,root,launcher,schema,expected_value_domain_ids,max_attempts=2,usage_sink=None):
    last_error=None; prior_failure=None
    partition_fields=tuple(schema["partitionRequiredFields"])
    for attempt in range(1,max_attempts+1):
        session=str(uuid4()); value=None
        log(f"inspector:{name}: start attempt={attempt}/{max_attempts} session={session}")
        finding_shape={"id":"stable-id","defectKind":"missing-requirement|contradiction|infeasible-boundary|incomplete-propagation|unprovable-acceptance","candidateDefect":"defect in the frozen task design, not unfinished code","taskEvidence":["bound-task.md:line"],"codeEvidence":["services/or/packages/or/core/or/extensions/path:line"],"requiredTaskChange":"architecturally complete task-authority change"}
        prompt=json.dumps({"inputFingerprint":fingerprint,"document":str(document),"workspaceRoot":str(root),"partition":spec,"sessionUuid":session,"priorAttemptFailure":prior_failure,"reviewSubject":{"kind":"pre-implementation architecture candidate","taskIsAuthority":True,"codeIsReadOnlyBaseline":True,"implementationCompletionIsOutOfScope":True},"discoveryContract":{"repositoryRoot":str(root),"methods":{method:{"capability":capability} for method,capability in DISCOVERY_CAPABILITIES.items()}},"persistedContractContract":{"allowedDomainIds":sorted(expected_value_domain_ids),"coverage":"complete" if name in {"contract","persistence"} else "relevant-subset","forbiddenIdKinds":["proof","matrix"]},"findingContract":{"shape":finding_shape,"rule":"A finding is valid only when the frozen task omits, contradicts, makes infeasible, incompletely propagates, or cannot prove an architectural requirement. Legacy or not-yet-implemented code is expected baseline evidence and is never by itself a finding. If the task already specifies the canonical owner, required end state, propagation, prohibited legacy behavior, and acceptance proof, do not fail because current code has not implemented it."},"toolPolicy":{"source":"Begin with lean_ctx_ctx_compose; use lean_ctx_ctx_read and lean_ctx_ctx_search instead of native read, grep, find, or ls.","dependency":"Use bounded ContextUnity code_map_query explain/impact/path calls and lean_ctx_ctx_callgraph for callers and dependency paths; never request doctor or broad inventories.","plannerAuthority":"Use Planner MemPalace only with planner-scoped task, roadmap, or plan queries for authority; never use it as source-code evidence."},"instruction":"Review the frozen task design against the read-only current code baseline. Return exactly one JSON object with exactly these top-level keys: id, status, inputFingerprint, evidence, findings, discovery, persistedContractMappings, isolated, readOnly. findings is an array of objects exactly matching findingContract.shape; fail requires at least one candidate-design defect and pass requires findings=[]. Never report implementation incompleteness, legacy symbols, or missing product-code changes as a finding unless they prove a specific omission, contradiction, infeasible boundary, incomplete propagation, or unprovable acceptance condition in the task itself. taskEvidence must cite the bound task; codeEvidence must cite repository code. persistedContractMappings contains only allowed domain IDs. discovery must exactly match discoveryContract and record complete bounded searches. Preserve substantive prior FAIL content only if it satisfies this candidate-defect contract. Do not return markdown or extra keys."})
        try:
            value=launch(launcher,prompt,session,root,partition_fields,usage_sink=usage_sink,usage_context={"role":"inspector","partition":name,"attempt":attempt})
            check_partition(value,name,fingerprint,schema,expected_value_domain_ids,document)
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


def run_coordinator(partitions,fingerprint,launcher,root,procedure,schema,contract,expected_persisted_contract_ids,max_attempts=2,candidate_authority=None,usage_sink=None):
    source_findings=[
        {"ref":f"{item['id']}:{index}","partition":item["id"],"finding":finding,"evidence":item["evidence"]}
        for item in partitions
        for index,finding in enumerate(item["findings"],1)
    ]
    recommendation_fields=["id","sourceFindings","invariant","rootCause","canonicalOwner","requiredChange","propagation","prohibitedShortcuts","acceptanceProof","evidence"]
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
    }
    prior_failure=None; last_error=None
    for attempt in range(1,max_attempts+1):
        coordinator=str(uuid4()); raw_result=None
        log(f"coordinator: start attempt={attempt}/{max_attempts} session={coordinator} source-findings={len(source_findings)}")
        prompt=json.dumps({"inputFingerprint":fingerprint,"candidateAuthority":candidate_authority or {},"partitions":partitions,"sourceFindings":source_findings,"priorAttemptFailure":prior_failure,"outputContract":{"topLevelRequired":["coordinator"],"coordinatorRequired":["verdict","resolvedFindings","reconciledRecommendations"],"recommendationRequired":recommendation_fields,"recommendationShape":recommendation_shape},"recommendationPolicy":{"goal":"Reconcile only genuine defects in the frozen task architecture candidate.","resolution":"Put a source ref in resolvedFindings when its required architectural state is already fully and unambiguously specified by candidateAuthority. Current legacy or not-yet-implemented code is not a candidate defect.","requirements":["State the violated invariant and root cause.","Name the canonical owner boundary where the invariant must be fixed.","Describe the required task end state, not product-code completion or code snippets.","Cover every affected caller, transport, storage path, backend, compatibility surface, and lifecycle transition.","Name prohibited symptom-level shortcuts.","Specify acceptance proof."],"coverage":"Every sourceFindings ref must occur exactly once in resolvedFindings or across reconciledRecommendations.sourceFindings."},"instruction":"Use only candidateAuthority, validated partitions, and sourceFindings; do not search or call tools. Independently test every finding against the frozen task authority. Resolve findings that merely observe unfinished/legacy implementation or restate requirements already complete in the task. Return exactly one JSON object whose only top-level key is coordinator and whose coordinator has exactly verdict, resolvedFindings, and reconciledRecommendations. PASS requires every source finding resolved and no recommendations. FAIL requires at least one architecturally complete recommendation. Never require product implementation before G0. Do not emit markdown or extra keys."})
        try:
            raw_result=launch(launcher,prompt,coordinator,root,("coordinator",),usage_sink=usage_sink,usage_context={"role":"coordinator","partition":"coordinator","attempt":attempt})
            if set(raw_result)!={"coordinator"} or not isinstance(raw_result["coordinator"],dict):
                raise RunnerError("coordinator must return only one coordinator object")
            model_result=raw_result["coordinator"]
            if set(model_result)!={"verdict","resolvedFindings","reconciledRecommendations"}:
                raise RunnerError("coordinator model output must contain verdict, resolvedFindings, and reconciledRecommendations only")
            result={"inputFingerprint":fingerprint,"runtime":str(procedure["runtime"]),"capabilities":list(schema["requiredCapabilities"]),"isolated":True,"readOnly":True,"authoritativeSessionUuids":[coordinator],"persistedContractIds":sorted(expected_persisted_contract_ids),"partitions":partitions,"coordinator":{"sessionUuid":coordinator,"verdict":model_result["verdict"],"findingsReconciled":True,"persistedContractsReconciled":True,"resolvedFindings":model_result["resolvedFindings"],"reconciledRecommendations":model_result["reconciledRecommendations"]},"usage":summarize_usage(usage_sink or [])}
            validate_result(contract,schema,result,expected_value_domain_ids=expected_persisted_contract_ids)
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
def record_attempt(document,fingerprint,verdict,coordinator,partitions,findings,usage=None):
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
    attempts.append(entry)
    payload["attempts"]=attempts
    document.write_text(replace_section(text,"ACDD architecture admission",fence()+"yaml\n"+yaml.safe_dump(payload,sort_keys=False).rstrip()+"\n"+fence()),encoding="utf-8")
def add_pass(document,fingerprint,adapter,author,result):
    text=document.read_text(encoding="utf-8"); evidence_id="architecture.runner."+fingerprint.split(":",1)[1][:12]
    review={"apiVersion":"acdd/gate-evidence/v1","kind":"review","id":evidence_id,"gate":"architecture/v1","inputFingerprint":fingerprint,"adapter":adapter,"sessionUuid":result["coordinator"]["sessionUuid"],"authorSessionUuid":author,"reviewer":"acdd architecture runner","independent":True,"terminalVerdict":"PASS","authoritySources":[document.name],"productionPaths":["four independent partitions"],"directCallers":["partition:callers"],"alternateCallers":["partition:authority"],"contradictions":[],"impactAxes":{"architecture":"reviewed"},"matrixMappings":["partition:contract"],"proofMappings":["partition:persistence"],"findings":[],"inventoryComplete":True,"decisionsResolved":True,"callerCoverageComplete":True,"persistedContractChange":bool(result["persistedContractIds"]),"persistedContractMappings":list(result["persistedContractIds"]),"discoveryComplete":True,"verification":result}
    old=markdown_sections(text).get("ACDD gate evidence","").strip(); dumped=yaml.safe_dump(review,sort_keys=False).rstrip(); opening=fence()+"yaml\n"; closing="\n"+fence()
    if old==opening+"[]"+closing: body=opening+dumped+closing
    elif old.startswith(opening) and old.endswith(closing): body=old[:-len(fence())]+"\n---\n"+dumped+closing
    else: raise RunnerError("gate evidence must be a YAML fence")
    text=replace_section(text,"ACDD gate evidence",body)
    mark=chr(96); row="| "+mark+"architecture/v1"+mark+" | "+mark+"pass"+mark+" | evidence="+evidence_id+" | "+mark+fingerprint+mark+" | "+mark+utc()+mark+" |"
    text=re.sub(r"(?m)^\| "+re.escape(mark)+r"architecture/v1"+re.escape(mark)+r" \|.*$",row,text)
    document.write_text(text,encoding="utf-8")
def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document",type=Path,required=True)
    parser.add_argument("--workspace-root",type=Path,required=True)
    parser.add_argument("--profile",type=Path,required=True)
    parser.add_argument("--receipt-contract",type=Path,required=True)
    parser.add_argument("--adapter",action="append",required=True)
    check_group=parser.add_mutually_exclusive_group(required=True)
    check_group.add_argument("--check-command")
    check_group.add_argument("--check-arg",action="append",dest="check_args")
    parser.add_argument("--author-session",default=str(uuid4()))
    args=parser.parse_args(argv)
    root=args.workspace_root.resolve(); document=args.document.resolve(); fingerprint=None; usage_records=[]
    try:
        sections=markdown_sections(document.read_text(encoding="utf-8"))
        if "ACDD contract changes" in sections:
            log("fingerprint: preserving historical baseline for declared contract change")
        else:
            log("fingerprint: recording current semantic fingerprint")
            subprocess.run([sys.executable,str(Path(__file__).with_name("record_fingerprint.py")),"--document",str(document),"--write"],cwd=root,check=True)
        log("preflight: running bound-task drift, contract, shape, and admission checks")
        if args.check_args is not None:
            check_run=subprocess.run(args.check_args,cwd=root,check=False)
        else:
            check_run=subprocess.run(args.check_command,cwd=root,shell=True,check=False)
        if check_run.returncode:
            raise RunnerError("check failed before architecture launch")
        log("preflight: PASS")

        core,adapters=load_core(args.profile.resolve()),_adapter_args(args.adapter)
        task_adapter=adapters["task"].resolve()
        adapter=load_adapter(task_adapter,"task",core,allowed_root=root)
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
        contract=load_yaml((task_adapter.parent/procedure["contract"]).resolve())
        schema=core.architecture_verification_schema
        if schema is None: raise RunnerError("task profile has no architecture schema")
        validate_contract(contract,schema)
        inspectors={item["id"]:item for item in contract["inspectors"]}
        maximum=int(schema["maxParallelInspectors"])
        if len(inspectors)!=4 or maximum!=4: raise RunnerError("architecture/v1 requires exactly four inspectors")
        log("contract: loaded four partitions: "+", ".join(inspectors))

        candidate=fingerprint_architecture_candidate(
            document=document,
            adapters=tuple(path.resolve() for path in adapters.values()),
            workspace_root=root,
        )
        fingerprint=candidate.sha256
        log(
            "fingerprint: candidate="+fingerprint
            +" semantic="+candidate.semantic_sha256
            +" code="+candidate.code_sha256
        )
        text=document.read_text(encoding="utf-8")
        expected_persisted_contract_ids=frozenset(
            domain.id
            for domain in parse_value_domains(
                text,
                workspace_root=root,
                declared_paths=frozenset(item.path for item in parse_inputs(text)),
                semantic_ids=frozenset(semantic_task_fingerprint(text).ids),
            )
        )
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
            candidate_authority=semantic_candidate_authority(text),
            usage_sink=usage_records,
        )
        log("snapshot: rechecking frozen task and allowed code inputs")
        current_candidate=fingerprint_architecture_candidate(
            document=document,
            adapters=tuple(path.resolve() for path in adapters.values()),
            workspace_root=root,
        )
        if current_candidate.sha256 != fingerprint:
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
        record_attempt(document,fingerprint,verdict,coordinator,partitions,findings,summarize_usage(usage_records))
        if verdict=="PASS":
            add_pass(document,fingerprint,adapter["id"],args.author_session,result)
            log("terminal: PASS evidence and receipt written")
        return 0 if verdict=="PASS" else 1
    except (RunnerError,ArchitectureGovernorError,ArchitectureVerificationError,ContractError,subprocess.CalledProcessError,OSError,KeyError,TypeError,ValueError) as exc:
        log("blocked: "+str(exc))
        if fingerprint:
            try:
                blocked_findings=exc.findings if isinstance(exc,RunnerError) and exc.findings else [{"id":"runner","partition":"runner","summary":str(exc)[:512],"evidence":[]}]
                blocked_partitions=exc.partitions if isinstance(exc,RunnerError) else []
                record_attempt(document,fingerprint,"BLOCKED",None,blocked_partitions,blocked_findings,summarize_usage(usage_records))
            except Exception: pass
        return 2
if __name__=="__main__": raise SystemExit(main())
