#!/usr/bin/env python3
"""Fail-closed concurrent architecture/v1 runner."""
from __future__ import annotations
import argparse, concurrent.futures, json, re, subprocess, sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
import yaml
from acdd_fingerprint import fingerprint_architecture_code_inputs, markdown_sections
from architecture_governor import ArchitectureGovernorError, parse_architecture_admission, validate_architecture_admission
from architecture_verification import ArchitectureVerificationError, load_yaml, validate_contract, validate_result
from validate_acdd import ContractError, _adapter_args, load_adapter, load_core

class RunnerError(RuntimeError): pass
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
def launch(binding, prompt, session, cwd, required=()):
    if binding.get("kind")!="command" or binding.get("promptTransport")!="final-argument": raise RunnerError("architecture launchers must be command/final-argument")
    target,args=binding.get("target"),binding.get("arguments")
    if not isinstance(target,str) or not isinstance(args,list) or not all(isinstance(v,str) for v in args): raise RunnerError("invalid architecture launcher")
    run=subprocess.run([target,*(v.replace("{sessionUuid}",session) for v in args),prompt],cwd=cwd,text=True,capture_output=True,check=False)
    if run.returncode: raise RunnerError("launcher failed: "+(run.stderr or run.stdout)[-4096:])
    return parse_launcher_output(run.stdout,required)
def check_partition(value, ident, fingerprint):
    required={"id","status","inputFingerprint","evidence","findings","discovery","persistedContractMappings","isolated","readOnly"}
    if set(value)!=required or value["id"]!=ident or value["inputFingerprint"]!=fingerprint: raise RunnerError("malformed partition "+ident)
    if value["status"] not in {"pass","fail"} or value["isolated"] is not True or value["readOnly"] is not True: raise RunnerError("partition not terminal/read-only/isolated: "+ident)
    methods=value.get("discovery",{}).get("methods") if isinstance(value.get("discovery"),dict) else None
    if not isinstance(value["evidence"],list) or not value["evidence"] or not isinstance(methods,dict): raise RunnerError("partition evidence/discovery missing: "+ident)
    if any(not isinstance(methods.get(name),dict) or methods[name].get("complete") is not True for name in ("exactText","structural","dependency")): raise RunnerError("partition discovery incomplete: "+ident)

def run_inspector(name,spec,fingerprint,document,root,launcher,partition_fields,max_attempts=2):
    output_contract={"required":list(partition_fields),"status":["pass","fail"],"evidence":"non-empty bounded file:line list","findings":"bounded list","discovery":{"methods":{"exactText":{"complete":True},"structural":{"complete":True},"dependency":{"complete":True}}},"persistedContractMappings":"list","isolated":True,"readOnly":True}
    last_error=None
    for attempt in range(1,max_attempts+1):
        session=str(uuid4())
        log(f"inspector:{name}: start attempt={attempt}/{max_attempts} session={session}")
        prompt=json.dumps({"inputFingerprint":fingerprint,"document":str(document),"workspaceRoot":str(root),"partition":spec,"sessionUuid":session,"toolPolicy":{"source":"Begin with lean_ctx_ctx_compose; use lean_ctx_ctx_read and lean_ctx_ctx_search instead of native read, grep, find, or ls.","dependency":"Use bounded ContextUnity code_map_query explain/impact/path calls and lean_ctx_ctx_callgraph for callers and dependency paths; never request doctor or broad inventories.","plannerAuthority":"Use Planner MemPalace only with planner-scoped task, roadmap, or plan queries for authority; never use it as source-code evidence."},"outputContract":output_contract,"instruction":"Return exactly one JSON object matching outputContract. Remain isolated and read-only. Do not emit markdown or extra keys."})
        try:
            value=launch(launcher,prompt,session,root,partition_fields)
            check_partition(value,name,fingerprint)
            log(f"inspector:{name}: finish status={value['status']} attempt={attempt}")
            return value
        except RunnerError as exc:
            last_error=exc
            log(f"inspector:{name}: transport/schema failure attempt={attempt}: {exc}")
    raise RunnerError(f"inspector {name} exhausted {max_attempts} transport/schema attempts: {last_error}")
def replace_section(text,title,body):
    marker="## "+title
    if marker not in text: return text.rstrip()+"\n\n"+marker+"\n\n"+body.rstrip()+"\n"
    return re.sub(r"(?ms)^"+re.escape(marker)+r"\n.*?(?=^## |\Z)",marker+"\n\n"+body.rstrip()+"\n\n",text)
def record_attempt(document,fingerprint,verdict,coordinator,partitions,findings):
    text=document.read_text(encoding="utf-8"); prior=parse_architecture_admission(text)
    attempts=[{"inputFingerprint":x.input_fingerprint,"verdict":x.verdict,"recordedAt":x.recorded_at} for x in prior.attempts]
    entry={"inputFingerprint":fingerprint,"verdict":verdict,"recordedAt":utc()}
    if coordinator: entry["coordinatorSession"]=coordinator
    if partitions: entry["partitionStatuses"]={x["id"]:x["status"] for x in partitions}
    if findings: entry["findings"]=findings
    attempts.append(entry)
    payload={"apiVersion":"acdd/architecture-admission/v1","kind":"architecture-admission","maxMaterialAttempts":prior.max_material_attempts,"candidateSet":[{"path":x.path,"sha256":x.sha256} for x in prior.candidate_set],"attempts":attempts}
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
    parser.add_argument("--check-command",required=True)
    parser.add_argument("--author-session",default=str(uuid4()))
    args=parser.parse_args(argv)
    root=args.workspace_root.resolve(); document=args.document.resolve(); fingerprint=None
    try:
        sections=markdown_sections(document.read_text(encoding="utf-8"))
        if "ACDD contract changes" in sections:
            log("fingerprint: preserving historical baseline for declared contract change")
        else:
            log("fingerprint: recording current semantic fingerprint")
            subprocess.run([sys.executable,str(Path(__file__).with_name("record_fingerprint.py")),"--document",str(document),"--write"],cwd=root,check=True)
        log("preflight: running bound-task drift, contract, shape, and admission checks")
        if subprocess.run(args.check_command,cwd=root,shell=True,check=False).returncode:
            raise RunnerError("check failed before architecture launch")
        log("preflight: PASS")

        core,adapters=load_core(args.profile.resolve()),_adapter_args(args.adapter)
        task_adapter=adapters["task"].resolve()
        adapter=load_adapter(task_adapter,"task",core,allowed_root=root)
        procedure=adapter["gateProcedures"]["architecture/v1"]
        launchers=procedure.get("launchers") if isinstance(procedure,dict) else None
        if not isinstance(launchers,dict): raise RunnerError("runner requires split launchers")
        contract=load_yaml((task_adapter.parent/procedure["contract"]).resolve())
        schema=core.architecture_verification_schema
        if schema is None: raise RunnerError("task profile has no architecture schema")
        validate_contract(contract,schema)
        inspectors={item["id"]:item for item in contract["inspectors"]}
        maximum=int(schema["maxParallelInspectors"])
        if len(inspectors)!=4 or maximum!=4: raise RunnerError("architecture/v1 requires exactly four inspectors")
        partition_fields=tuple(schema["partitionRequiredFields"])
        result_fields=tuple(schema["resultRequiredFields"])
        log("contract: loaded four partitions: "+", ".join(inspectors))

        fingerprint=fingerprint_architecture_code_inputs(
            document=document,
            adapters=tuple(path.resolve() for path in adapters.values()),
            workspace_root=root,
        ).sha256
        text=document.read_text(encoding="utf-8")
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
                partition_fields,
            )

        log("inspectors: launching one parallel wave of four Pi processes")
        with concurrent.futures.ThreadPoolExecutor(max_workers=maximum) as pool:
            outputs=dict(zip(inspectors,pool.map(run_one,inspectors)))
        partitions=[outputs[name] for name in inspectors]
        log("inspectors: all four outputs validated")

        coordinator=str(uuid4())
        log(f"coordinator: start session={coordinator}")
        prompt=json.dumps({"inputFingerprint":fingerprint,"document":str(document),"workspaceRoot":str(root),"partitions":partitions,"sessionUuid":coordinator,"outputContract":{"required":list(result_fields)},"instruction":"Reconcile every partition and return exactly one full coordinator result JSON object. Do not modify partition evidence. Do not emit markdown or extra keys."})
        result=launch(launchers["coordinator"],prompt,coordinator,root,result_fields)
        log("coordinator: output received; validating terminal result")
        validate_result(contract,schema,result)
        if result.get("inputFingerprint")!=fingerprint or result.get("partitions")!=partitions:
            raise RunnerError("coordinator result conflicts with partition evidence")
        findings=[{"id":item["id"]+"-"+str(index),"partition":item["id"],"summary":str(finding).replace("\n"," ")[:512],"evidence":item["evidence"][:4]} for item in partitions for index,finding in enumerate(item["findings"],1)]
        verdict=result["coordinator"]["verdict"]
        log(f"terminal: recording verdict={verdict} findings={len(findings)}")
        record_attempt(document,fingerprint,verdict,coordinator,partitions,findings)
        if verdict=="PASS":
            add_pass(document,fingerprint,adapter["id"],args.author_session,result)
            log("terminal: PASS evidence and receipt written")
        return 0 if verdict=="PASS" else 1
    except (RunnerError,ArchitectureGovernorError,ArchitectureVerificationError,ContractError,subprocess.CalledProcessError,OSError,KeyError,TypeError,ValueError) as exc:
        log("blocked: "+str(exc))
        if fingerprint:
            try: record_attempt(document,fingerprint,"BLOCKED",None,[],[{"id":"runner","partition":"runner","summary":str(exc)[:512],"evidence":[]}])
            except Exception: pass
        return 2
if __name__=="__main__": raise SystemExit(main())
