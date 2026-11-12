'use strict';

// FCI-M02: read-only local Git source verification. Does not prove remote HEAD,
// real runtime behavior, Engineer approval, or test execution.
const fs=require('fs');
const path=require('path');
const {spawnSync}=require('child_process');
const {probeGitRepository,runGit}=require('../git');
const {sha256}=require('../io');
const SHA40=/^[a-f0-9]{40}$/;
const SHA256=/^[a-f0-9]{64}$/;
const MAX_SOURCE_BYTES=1024*1024;

function inspectProject(repo){
  if(!repo || typeof repo.path!=='string' || !SHA40.test(repo.head||'')) return {
    status:'BLOCKED',code:'INVALID_REPOSITORY_PIN'
  };
  const state=probeGitRepository(repo.path);
  if(state.status!=='RESOLVED') return {status:'BLOCKED',code:'SOURCE_NOT_VERIFIED',reason:state.reason||'Git unavailable'};
  if(path.resolve(repo.path)!==state.top_level) return {status:'BLOCKED',code:'REPOSITORY_ROOT_MISMATCH'};
  if(state.head!==repo.head) return {
    status:'STALE',code:'STALE_HEAD',expected_head:repo.head,observed_head:state.head
  };
  if(repo.branch && state.branch!==repo.branch) return {
    status:'STALE',code:'STALE_BRANCH',expected_branch:repo.branch,observed_branch:state.branch
  };
  if(!state.clean) return {status:'BLOCKED',code:'DIRTY_WORKTREE',dirty_count:state.dirty_entry_count};
  return {
    status:'VERIFIED',scope:'LOCAL_GIT_HEAD_ONLY',root:state.top_level,
    head:state.head,branch:state.branch,clean:true
  };
}

function safeRepoPath(rel){
  if(typeof rel!=='string' || rel.length===0 || rel.length>500 ||
      rel.includes('\\') || rel.includes('\0') || rel.includes(':') ||
      rel.startsWith('/') || rel.endsWith('/') || rel.includes('//') ||
      !/^[A-Za-z0-9._\/ -]+$/.test(rel)) return false;
  return rel.split('/').every(part=>part!=='.' && part!=='..' && part.length>0);
}

function inspectSource(project,source){
  if(!project||project.status!=='VERIFIED') return {status:'BLOCKED',code:'SOURCE_ROOT_NOT_VERIFIED'};
  if(!source||typeof source.id!=='string'||!safeRepoPath(source.path)||!SHA256.test(source.sha256||'')) {
    return {status:'BLOCKED',code:'INVALID_SOURCE_PIN',id:source&&source.id};
  }
  const segments=source.path.split('/');
  let current=project.root;
  try {
    for(let i=0;i<segments.length;i++){
      current=path.join(current,segments[i]);
      const stat=fs.lstatSync(current);
      if(stat.isSymbolicLink()) return {status:'BLOCKED',code:'SOURCE_SYMLINK_DENIED',id:source.id,path:source.path};
      if(i<segments.length-1 && !stat.isDirectory()) return {status:'BLOCKED',code:'SOURCE_NOT_FILE',id:source.id,path:source.path};
      if(i===segments.length-1 && !stat.isFile()) return {status:'BLOCKED',code:'SOURCE_NOT_FILE',id:source.id,path:source.path};
    }
  } catch {
    return {status:'BLOCKED',code:'SOURCE_NOT_FOUND',id:source.id,path:source.path};
  }
  const tracked=runGit(project.root,['ls-files','--error-unmatch','--',source.path]);
  if(!tracked.ok || tracked.stdout.split(/\r?\n/).filter(Boolean).length!==1 ||
     tracked.stdout!==source.path) return {
    status:'BLOCKED',code:'SOURCE_NOT_TRACKED',id:source.id,path:source.path
  };
  const size=runGit(project.root,['cat-file','-s','HEAD:'+source.path]);
  if(!size.ok) return {status:'BLOCKED',code:'SOURCE_NOT_IN_HEAD',id:source.id,path:source.path};
  const bytes=Number(size.stdout);
  if(!Number.isSafeInteger(bytes)||bytes<0||bytes>MAX_SOURCE_BYTES) return {
    status:'BLOCKED',code:'SOURCE_SIZE_LIMIT',id:source.id,path:source.path,size:bytes
  };
  const result=spawnSync('git',['-C',project.root,'show','HEAD:'+source.path],{
    windowsHide:true,encoding:null,maxBuffer:MAX_SOURCE_BYTES+8192
  });
  if(result.status!==0||result.error||!Buffer.isBuffer(result.stdout)||
     result.stdout.length!==bytes) return {
    status:'BLOCKED',code:'SOURCE_READ_FAILED',id:source.id,path:source.path
  };
  const actual=sha256(result.stdout);
  if(actual!==source.sha256) return {
    status:'STALE',code:'SOURCE_DIGEST_MISMATCH',id:source.id,path:source.path,
    expected_sha256:source.sha256,observed_sha256:actual
  };
  return {id:source.id,kind:source.kind,path:source.path,status:'VERIFIED',
    sha256:actual,head:project.head,size:bytes,scope:'PINNED_GIT_CONTENT_ONLY'};
}
module.exports={inspectProject,inspectSource,safeRepoPath,MAX_SOURCE_BYTES};
