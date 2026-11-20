"""R5 callable ASGI service surface (unhosted and disabled by default).

A ChatGPT service connector may call POST /v1/forge/execute after explicit
authorization. There is NO model tool registration, worker-account delegation
or deployment in this module. This route cannot select shell commands, tool
grants, signing keys or provider configuration. Those are server-owned deps.

Production requires separately approved TLS/service gateway, scoped bot
credentials, host signing key, monetary cap, and isolated candidate activation.
"""
from __future__ import annotations
import hmac
import json

from integrations.chatgpt.scoped_broker import Denied

ROUTE="/v1/forge/execute"
LIMIT=64000
FIELDS=frozenset(("writer_packet","reviewer_packet","source_sha","source_tree",
                  "source_paths","task","nonce_prefix","repo_id"))

class ForgeOperatorASGI:
    def __init__(self,pilot,*,bearer_secret:bytes,enabled=False):
        if not isinstance(bearer_secret,bytes) or len(bearer_secret)<32:
            raise Denied("HOST_CALLER_SECRET_REQUIRED")
        self.pilot=pilot
        self.key=bearer_secret
        self.enabled=enabled
    async def __call__(self,scope,receive,send):
        async def reply(status,obj):
            raw=json.dumps(obj,sort_keys=True,ensure_ascii=True,
                           separators=(",",":")).encode()
            await send({"type":"http.response.start","status":status,
                        "headers":[(b"content-type",b"application/json"),
                                   (b"cache-control",b"no-store"),
                                   (b"x-content-type-options",b"nosniff")]})
            await send({"type":"http.response.body","body":raw})
        if scope.get("type")!="http" or scope.get("path")!=ROUTE or scope.get("method")!="POST":
            return await reply(404,{"error":"NOT_FOUND"})
        # Never accept a bearer token or model prompt as a substitute for the
        # separately authorized deployment gate.
        if not self.enabled:
            return await reply(503,{"error":"R5_HOST_ACTIVATION_REQUIRED"})
        headers={}
        for item in scope.get("headers",[]):
            if not isinstance(item,tuple) or len(item)!=2:continue
            key,value=item
            if key.lower() in headers:
                return await reply(400,{"error":"DUPLICATE_HEADERS"})
            headers[key.lower()]=value
        if headers.get(b"content-type",b"").split(b";")[0].strip().lower()!=b"application/json":
            return await reply(415,{"error":"JSON_CONTENT_TYPE_REQUIRED"})
        authorization=headers.get(b"authorization",b"")
        if not hmac.compare_digest(authorization,b"Bearer "+self.key):
            return await reply(401,{"error":"UNAUTHORIZED"})
        body=b""
        for _ in range(32):
            event=await receive()
            if event.get("type")!="http.request":
                return await reply(400,{"error":"REQUEST_DISCONNECTED"})
            part=event.get("body",b"")
            if not isinstance(part,bytes):
                return await reply(400,{"error":"BODY_INVALID"})
            body+=part
            if len(body)>LIMIT:return await reply(413,{"error":"REQUEST_TOO_LARGE"})
            if not event.get("more_body",False):break
        else:
            return await reply(413,{"error":"REQUEST_CHUNK_LIMIT_EXCEEDED"})
        try:
            params=json.loads(body)
            if not isinstance(params,dict) or set(params)!=FIELDS:
                raise Denied("INVALID_OPERATION_SCHEMA")
            if (not isinstance(params["source_paths"],list) or len(params["source_paths"])>32
                or type(params["repo_id"]) is not int):
                raise Denied("INVALID_OPERATION_SCOPE")
            # Only this one host-owned handler exists. There is no pass-through
            # GitHub, shell, provider selection, or arbitrary tool method.
            out=self.pilot.run(**params)
            out={"mission":"FORGE-CHATGPT-INDEPENDENT-ENGINEERING-PILOT-R5",
                 "result":out,
                 "acceptance":"NOT_ACCEPTED" if not self.pilot.live else "REQUIRES_INDEPENDENT_G13",
                 "host_operational":bool(self.pilot.live)}
            return await reply(200,out)
        except Denied as exc:
            # No raw source, stack trace, credentials, or signer material.
            return await reply(403,{"error":"FORGE_POLICY_DENIED","reason":str(exc)[:100]})
        except (TypeError,ValueError,KeyError,UnicodeError):
            return await reply(400,{"error":"INVALID_INPUT"})
        except Exception:
            return await reply(500,{"error":"EXECUTION_FAILED_RECOVERY_REQUIRED"})
