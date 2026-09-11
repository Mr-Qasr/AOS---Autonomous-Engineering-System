# AOS Threat Model & Security Policy Architecture

## 1. Executive Summary & Attacker Model

In the Autonomous Engineering System (AOS), the primary threat actor modeled is **the autonomous coding agent itself**. 

Unlike conventional applications where external users are the untrusted boundary, AOS executes an autonomous LLM agent with code generation, shell invocation, and tool-use capabilities. The agent may exhibit:
- Hallucinated or errant actions.
- Goal drift or unbounded recursive loops.
- Prompt injection exploitation (e.g. malicious payloads hidden in ingested source repositories, issue trackers, or documentation).
- Accidental or opportunistic attempts to bypass testing, escape isolation, or modify protected branches.

**Invariant (Master Spec §8):** An agent may request an action; only the policy engine — never the agent — decides whether it executes.

---

## 2. Security & Policy Boundary Scope

### Phase 0 Scope
Phase 0 defines the **declarative contracts** (`Policy`, `PolicyRule`), canonical schemas, and threat taxonomy. It establishes the constitutional rules that the platform must adhere to.

### Deferred Enforcement Boundary
Phase 0 does **NOT** implement an executable policy evaluation engine, Policy Decision Point (PDP), Policy Enforcement Point (PEP), or runtime authorization interceptor. Runtime enforcement is implemented in:
- **Phase 2:** Ephemeral container sandbox isolation, network egress blocking, and resource ceilings.
- **Phase 3:** MCP tool scoping and path traversal protection.
- **Phase 12:** Release gates, cryptographic approval validation, and paid compute budget ceilings.

---

## 3. STRIDE Threat Analysis & Action Mapping (Master Spec §8)

The table below maps every action from Master Specification §8 to its default policy, STRIDE classification, the impact if bypassed by an uncontained agent, and the corresponding policy rule.

| # | Action | Default Policy | STRIDE Classification | Attacker Bypass Impact (If Policy Bypassed) | Mitigating Policy Rule | Enforcing Layer (Phase) |
|---|---|---|---|---|---|---|
| 1 | **Read project repo** | Allowed in project scope | **Information Disclosure** | Agent reads sensitive host directories (`/etc/passwd`, `C:\Users\*`), keys, or out-of-scope project secrets. | `repo.read` (`scope: project`) | Phase 2/3 Sandbox & MCP Tool |
| 2 | **Write code** | Task branch / workspace only | **Tampering** | Agent modifies production `main` branch directly, taints other task workspaces, or writes to host OS binaries. | `repo.write` (`branch_prefix: task/`) | Phase 2 Container mount & Git wrapper |
| 3 | **Terminal** | Sandboxed + resource / command policy | **Elevation of Privilege** | Agent executes arbitrary commands on the host machine, executes fork-bombs, or mines cryptocurrency. | `terminal.execute` (`sandboxed: true`) | Phase 2 Ephemeral Docker container |
| 4 | **Network** | Deny by default; allow required domains | **Information Disclosure / Denial of Service** | Agent exfiltrates private intellectual property, connects to external command-and-control servers, or participates in DDoS. | `network.egress` (Effect: `deny`) | Phase 2 Docker network driver (`none`) |
| 5 | **Inbound ports** | Deny, no exceptions | **Elevation of Privilege** | Agent launches a listening daemon, backdoor SSH service, or rogue web server, opening host ports to attackers. | `network.bind_inbound` (Effect: `deny`) | Phase 2 / Phase 11 Mesh network isolation |
| 6 | **Secrets access** | Just-in-time, narrow scope, redacted | **Information Disclosure** | Agent dumps API keys or deployment credentials into public code commits, issue responses, or event streams. | `secrets.access` (`just_in_time: true`) | Phase 2 OpenBao injection & log sanitizer |
| 7 | **Protected merge** | Requires Approval object | **Tampering / Repudiation** | Agent unilaterally merges unverified, hallucinated, or broken code into the protected `main` branch. | `git.protected_merge` (`requires_approval: true`) | Phase 12 Release Gate |
| 8 | **Production deploy** | Requires Approval object | **Elevation of Privilege** | Agent deploys unvalidated code directly to live production environments, risking business disruption. | `deploy.production` (`requires_approval: true`) | Phase 12 Release Gate |
| 9 | **Paid compute** | Requires budget check + Approval object | **Denial of Service (Financial)** | Unchecked loops or multi-agent swarms deplete commercial API credits or cloud compute budgets. | `compute.paid` (`check_budget_ceiling: true`) | Phase 3 Gateway & Phase 12 Budget Gate |
| 10 | **Destructive operation** | Requires Approval object | **Tampering / Denial of Service** | Agent runs `rm -rf /`, drops database tables, deletes volume mounts, or force-prunes commit history. | `system.destructive_op` (`requires_approval: true`) | Phase 12 Approval Gate & Command filter |

---

## 4. Inbound Network & Remote Worker Containment

A critical non-negotiable rule of AOS is:
**Zero inbound open ports, ever.**

Remote worker compute nodes (introduced in Phase 11) communicate strictly via encrypted WireGuard / Headscale mesh membership. Under no circumstances may an agent request or receive permission to open or bind to a public listening port.

