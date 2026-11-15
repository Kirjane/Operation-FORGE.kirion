# Kirion ChatGPT worker identities (observed login required)
| Conversation / worker | Expected linked GitHub login | Typical function only; mission overrides |
|---|---|---|
| Nairu / Engineer Maintainer | Kirch-Nairu | Feature ownership, architecture, acceptance and human decisions |
| Jane | Kirion-Jane | Bounded implementation/QA as assigned |
| Nox | Kirion-Nox | Independent code/security/financial review as assigned |
| Lucien | Kirion-Lucien | Bounded implementation/integration/frontend as assigned |

Use a GitHub connector to check the actual login in **each** conversation. The model/persona label doesn't authenticate the account or grant permissions. No automatic opening of separate chats, no shared VM filesystem, no misattributed commits or independent review by the same code author. Handoffs consist of an exact-SHA issue/PR evidence pointer plus the next mission.
