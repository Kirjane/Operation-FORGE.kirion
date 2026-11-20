// Read-only ChatGPT connector boundary. No runtime or review independence claims.
export function createConnectorAdapter(api, bindings) {
  const sha = x => typeof x==="string" && /^[0-9a-f]{40}$/.test(x) && !/^0+$/.test(x);
  const fail = code => { throw Error(code); };
  const actor = Object.freeze({"Kirch-Nairu":291564617,"Kirion-Jane":335897759,"Kirion-Nox":339503629,"Kirion-Luci3n":359299805,"Kirion-Lucien":339001004,"k3nchinxd":319460416});
  const links = Object.freeze({...bindings});
  const roles=Object.freeze({maintainer:["Kirch-Nairu",["READ","PLAN","QA"]],writer:["Kirion-Jane",["READ","PREPARE_CANDIDATE"]],nox:["Kirion-Nox",["READ","SAME_CONTEXT_REVIEW"]],luci3n:["Kirion-Luci3n",["READ"]],delivery:["Kirch-Nairu",["READ","PREPARE_DELIVERY"]]});
  async function authenticate(login) {
    if(login==="Kirion-Lucien") fail("SUSPENDED_LEGACY_ACTOR");
    if(!Object.hasOwn(actor,login)||!Object.hasOwn(links,login)||typeof links[login]!=="string"||!links[login]) fail("ACCOUNT_UNBOUND");
    const who=await api.identity(links[login]);
    if(who?.login!==login||who?.id!==actor[login]) fail("ACTOR_MISMATCH");
    return {login,id:who.id};
  }
  async function repository(login,repo,requirePush=false) {
    if(typeof repo!=="string"||!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repo)||repo.split("/").some(s=>s==="."||s==="..")) fail("INVALID_REPOSITORY");
    if(typeof requirePush!=="boolean") fail("INVALID_PERMISSION_REQUEST");
    const identity=await authenticate(login);
    const data=await api.repository(links[login],repo);
    if(data?.repository_full_name!==repo||data?.permissions?.pull!==true) fail("REPOSITORY_READ_DENIED");
    if(requirePush&&data.permissions.push!==true) fail("REPOSITORY_WRITE_DENIED");
    return {identity,repo,pull:true,push:data.permissions.push===true};
  }
  async function pin(login, repo, branch, expectedSha, expectedTree) {
    if(typeof branch!=="string"||!/^[-A-Za-z0-9_]+(?:[./][-A-Za-z0-9_]+)*$/.test(branch)||branch.startsWith("-")||branch.startsWith("refs/")||branch.includes("..")||branch.split("/").some(x=>x.startsWith(".")||x.endsWith(".")||x.endsWith(".lock"))) fail("INVALID_BRANCH");
    if(!sha(expectedSha)||!sha(expectedTree)) fail("INVALID_OBJECT_ID");
    const observed=await repository(login,repo);
    const b=await api.branch(links[login],repo,branch);
    if(b?.name!==branch||b?.commit?.sha!==expectedSha||b?.commit?.commit?.tree?.sha!==expectedTree) fail("EXACT_HEAD_OR_TREE_DRIFT");
    return {...observed,branch,sha:expectedSha,tree:expectedTree};
  }
  async function authorizeScoped(role,operation,scope) {
    if(!Object.hasOwn(roles,role)||!roles[role][1].includes(operation)) fail("ROLE_OPERATION_DENIED");
    if(!scope||typeof scope.repoId!=="string"||!/^[1-9][0-9]*$/.test(scope.repoId)) fail("INVALID_REPOSITORY_ID");
    const login=roles[role][0];
    const pinned=await pin(login,scope.repo,scope.branch,scope.sha,scope.tree);
    const actual=await api.repository(links[login],scope.repo);
    if(String(actual?.id)!==scope.repoId||actual?.repository_full_name!==scope.repo||actual?.permissions?.pull!==true) fail("REPOSITORY_ID_OR_ACCESS_DRIFT");
    if(["PREPARE_CANDIDATE","PREPARE_DELIVERY"].includes(operation)&&actual.permissions.push!==true) fail("REPOSITORY_WRITE_DENIED");
    return {...pinned,repoId:scope.repoId,role,operation,status:"PREFLIGHT_ONLY",independentReview:false,mutationPerformed:false};
  }
  function dispatch() { return {status:"BLOCKED_SEPARATE_SESSION_REQUIRED",nativeLaunch:false,contextId:null,independentReview:false}; }
  function delivery() { fail("CORE_BROKER_AND_DURABLE_HOST_BRIDGE_REQUIRED"); }
  return Object.freeze({authenticate,repository,pin,authorizeScoped,dispatch,delivery});
}
