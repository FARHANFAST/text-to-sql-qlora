# Experiments

| Exp ID | Description | Model | Prompt | Fine-tuned? | Self-correct? | EX (dev) | 95% CI | Easy | Medium | Hard | Extra | EX (test) | Real-world EX | Avg latency | Cost / 1K queries | Predictions file |
|--------|-------------|-------|--------|-------------|----------------|----------|--------|------|--------|------|-------|-----------|---------------|-------------|-------------------|-------------------|
| 1 | Baseline, prompt v1 | pending | v1 | no | no | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 2 | Prompt v2 | pending | v2 | no | no | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 3 | Prompt v3 | pending | v3 | no | no | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 4 | QLoRA run A | pending | pending | yes | no | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 5 | QLoRA run B | pending | pending | yes | no | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 6 | Self-correction on best fine-tuned model | pending | pending | yes | yes | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 7 | 70B comparison (Groq) | pending | pending | no | no | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 8 | Real-world eval | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 9a | Real-world: schema descriptions | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 9b | Real-world: value hints + linking | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 9c | Real-world: schema pruning | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 9d | Real-world: self-consistency voting | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |

`EX (test)` is filled in only once per final configuration (best baseline, best fine-tuned model, best with self-correction, 70B) — see CLAUDE.md's dev-vs-test rule. All numbers come only from files in `results/` produced by real runs. A row stays "pending" until that run has actually happened.
