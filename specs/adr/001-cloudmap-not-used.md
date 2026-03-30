# ADR-001: CloudMap Not Used for ALB-Based App Routing

**Status:** Accepted
**Date:** 2026-03-29

## Context

The platform routes browser traffic to per-app containers via an ALB with path-based listener rules (`/workspace{id}/{appId}*`). Each workspace runs a single ECS service with a multi-container task (one container per app). All containers share the same private IP (the task's ENI), on different ports.

AWS CloudMap (Service Discovery) was evaluated as a potential simplification for task IP registration and app routing.

## Decision

CloudMap is not used. The controller registers task IPs to ALB target groups manually via boto3 after the task reaches RUNNING.

## Reasoning

CloudMap auto-registers a task's private IP/port to a **DNS namespace** when ECS starts the task. It is designed for service-to-service discovery — one service calling another by DNS name.

ALB target groups are a **separate system**. CloudMap DNS entries do not propagate to ALB target group registrations. There is no native AWS integration between CloudMap and ALB IP-mode target groups.

Concretely:

| Need | CloudMap | ALB Target Group |
|------|----------|-----------------|
| Internal service-to-service calls | Yes — DNS auto-registered | Not applicable |
| Browser traffic via ALB path routing | No — ALB ignores CloudMap DNS | Yes — requires explicit `register_targets` |

Since all user-facing traffic flows through the ALB, CloudMap would not remove the `wait_for_task_ip` → `register_targets` flow. It would add a second registration mechanism with no benefit.

CloudMap would only be worth revisiting if:
- Apps needed to call each other internally by name (service mesh)
- A non-ALB routing approach were adopted (e.g., per-workspace NLB or direct IP proxy)

## Consequences

The bootstrap flow retains the manual registration steps:

1. `wait_for_task_running(service_name)` — poll until ECS service scheduler starts a task
2. `wait_for_task_ip(task_arn)` — poll ENI attachment for `privateIPv4Address`
3. `register_task_to_tgs(task_arn, workspace_id, apps)` — call `elbv2.register_targets` for each app's TG

This adds ~30–60 s to bootstrap time (task cold start) but is unavoidable with IP-mode ALB target groups when the ECS service is created without a `loadBalancers` config.
