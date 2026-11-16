# Week 7 – Agent Orchestration: Recipe Box Sprint

**Repository:** https://github.com/Ezzgiturann/week7-recipe-box
**Agents:** Claude Code CLI sessions (`claude -p`), each started with its own prompt and tool allowlist.
**Raw logs:** every agent step, every tool call, and every refused tool call is in [`agent-logs/`](agent-logs/) (`*.jsonl`).

## 1. Part I – Concurrent agents

### Which two tasks
- **Task 1, Shopping list** (agent A): `GET /shopping-list?ids=1,2,3` returns the de-duplicated ingredients.
- **Task 2, Tag filter** (agent B): `GET /recipes?tag=breakfast` returns only matching recipes.

I wrote both prompts myself and made the open decisions before starting the agents. Shopping list: case/whitespace-insensitive de-dup, `"200 g flour"` and `"100 g flour"` kept apart, first-seen order, 404 for unknown ids, 422 for malformed ids. Tag filter: case-insensitive, repeated `tag` means OR, `[]` when nothing matches, 422 for an empty tag. The prompts are in [`agent-logs/prompt-a.txt`](agent-logs/prompt-a.txt) and [`agent-logs/prompt-b.txt`](agent-logs/prompt-b.txt).

### Worktree setup
```bash
git worktree add ../recipe-task-a -b task-a/shopping-list
git worktree add ../recipe-task-b -b task-b/tag-filter
```
Both agents were started from the same shell with `&` and then `wait`. Each `claude -p` session ran inside its own worktree:

| Agent | Worktree | Start | End |
|---|---|---|---|
| A – Shopping list | `../recipe-task-a` | 17:53:07 | 17:54:48 |
| B – Tag filter | `../recipe-task-b` | 17:53:07 | 17:54:56 |

They ran at the same time for about 1 min 40 s ([`agent-logs/timeline.txt`](agent-logs/timeline.txt)). Each worktree also had its own `recipes.db`, because the app puts the database next to `main.py`, so the agents could not touch each other's data.

### How I kept them from colliding
- **Separate directories and branches** through worktrees, so neither agent could see or edit the other's files.
- **Rules in both prompts:** change only `main.py` and `test_main.py`, do not touch existing endpoints, put new tests at the end of `test_main.py` under a separate heading (`# --- Shopping list ---` / `# --- Tag filter ---`), and do not commit.
- **I did all the integration myself.** I committed each agent's output unchanged, merged A, then merged B, and resolved the conflict.

### Collisions and risks – what actually happened
- **`main.py` merged automatically.** A added a new endpoint and the `re` import. B changed `list_recipes` and added the `Optional` and `Query` imports.
- **`test_main.py` conflicted.** Both prompts said "use a temporary database", and **both agents added a fixture with the same name, `temp_db`**, at the end of the file. A's fixture gave an empty database. B's fixture gave an empty database plus 4 seeded recipes.
- **Keeping both sides would have been silently wrong.** I tried the naive resolution in a scratch copy. The file then had two `def temp_db` (lines 40 and 90), the second replaced the first, and **all 20 tests still passed**. A probe test showed that the shopping-list tests then started with `['Pancakes', 'Omelette', 'Soup', 'Plain']`, which is B's seed data, instead of the empty database A had written them for. The text conflict hid a semantic conflict that the test suite could not detect.
- **My resolution** ([`2ec0206`](https://github.com/Ezzgiturann/week7-recipe-box/commit/2ec0206)): one `autouse` `temp_db` at the top of the file, and B's seed data moved into its own `tagged_recipes` fixture. Side benefit: the three starter tests stopped writing into the real `recipes.db`. Both agents had noticed that problem but left it alone as out of scope.
- **Integration check.** No agent tested the two features together, so I did it against the merged app with `uvicorn` ([`agent-logs/integration-check.md`](agent-logs/integration-check.md)). The ids from `GET /recipes?tag=breakfast` (1, 3, 4) passed to `GET /shopping-list` gave `["flour", "milk", "2 eggs", "salt"]`. `"Milk"` and `"milk"` were merged, and the order was first-seen. The 404 and 422 cases behaved as the prompts said.

## 2. Part II – Generator–critic loop (Task 3, Ingredient scaling)

The prompts are [`generator-prompt.txt`](agent-logs/loop/generator-prompt.txt) (Task 3 rules) and [`critic-rubric.txt`](agent-logs/loop/critic-rubric.txt) (correctness / tests / clarity, PASS or FAIL each, and APPROVE only if all three PASS). I wrote both.

### How the loop ran
[`run_loop.sh`](agent-logs/loop/run_loop.sh) ran it automatically in its own worktree (`../recipe-task-c`):
1. The **generator** writes or revises the code, and the script commits the result.
2. A **fresh critic session** reviews `git diff main...HEAD` against the rubric and ends with `VERDICT: APPROVE` or `VERDICT: REVISE`.
3. On `REVISE`, the critic's full report goes back to the **same generator session** (`--resume`), which revises.

Every round's output is saved as text:
- generator: [`roundN-generator.md`](agent-logs/loop/)
- critic: [`roundN-critic.md`](agent-logs/loop/)
- full tool logs: `roundN-*.jsonl`
- timeline: [`timeline.txt`](agent-logs/loop/timeline.txt)

### Rounds (transcript summary)

| Round | Generator commit | pytest | Correctness | Tests | Clarity | Critic's main finding | What the generator changed (from the previous round's finding) |
|---|---|---|---|---|---|---|---|
| 1 | [`230f262`](https://github.com/Ezzgiturann/week7-recipe-box/commit/230f262) | 43 passed | FAIL | FAIL | PASS | `"1-2 cloves"` → `"2-2"`, `"1,5 kg"` → `"2,5"`, `"1½"` → `"2½"` (silently wrong); missing tests for these | — |
| 2 | [`475e50b`](https://github.com/Ezzgiturann/week7-recipe-box/commit/475e50b) | 72 passed | FAIL | FAIL | PASS | `"½ cup"` not scaled, and a test locks that in; `"2-inch"` → `"4-inch"`; response shows `"factor": 2.0`, and the test missed it because `2.0 == 2` | Ambiguous lines left unchanged; Unicode/range tests added |
| 3 | [`1366a8d`](https://github.com/Ezzgiturann/week7-recipe-box/commit/1366a8d) | 90 passed | FAIL | PASS | PASS | `"1-1/2"` (US mixed number) read as the range 1 to ½ | Unicode fractions and ranges scaled; new `unscaled` list in the response; the test checks the raw JSON for `"factor":2` |
| 4 | [`ce17178`](https://github.com/Ezzgiturann/week7-recipe-box/commit/ce17178) | 105 passed | FAIL | PASS | PASS | `70%`, `180°C` scaled; 4300-digit amounts → 500; `-2 g` not flagged | `1-1/2` fixed; `⁄` slash; large numbers no longer crash |
| 5 | [`52a3ded`](https://github.com/Ezzgiturann/week7-recipe-box/commit/52a3ded) | 119 passed | FAIL | PASS | PASS | `"1 lb 4 oz"`, `"1 cup plus 2 tbsp"` scaled only by the first number, not reported; warns that 9 regexes form a fragile blacklist | % / ° excluded; 100-digit cap; signs flagged |
| 6 | [`80b8886`](https://github.com/Ezzgiturann/week7-recipe-box/commit/80b8886) | 133 passed | FAIL | PASS | PASS | Amounts not at the start (`"flour 200 g"`, `"Eggs: 2"`) are silently skipped | **Human decision applied:** one general rule (any second number → `unscaled`) replaced 8 special-case regexes; limitations documented in the docstring |

**That is 5 revision rounds (2–6), and every one answers the critic's previous report point by point.** The generator did not accept every point. In round 3 it kept `factor=1` returning the text unchanged, and in round 4 it kept `"2 3 eggs"` as is, and it explained why each time. A short excerpt from round 1:

> **Critic (round 1):** `"1,5 kg un"` with factor 2 → `"2,5 kg un"` … Turkish recipes use a comma as the decimal separator, so the user would get 40% less without any error. **VERDICT: REVISE**
>
> **Generator (round 2):** I agree with both FAIL findings and fixed them. `1,5` means 1.5 in Turkish, but `1,000` means a thousand, and the two cannot be told apart from the text. A wrong guess could be off by 1000×, so these lines are now left unchanged.

### Human intervention after round 5
After 5 rounds, Tests and Clarity had passed since round 3. Only Correctness kept failing, and each time on a rarer input. The round-5 critic also warned that the regex blacklist was getting fragile. **I made an orchestrator decision** ([`human-decision.txt`](agent-logs/loop/human-decision.txt)) and sent it to both agents ([`run_loop_continue.sh`](agent-logs/loop/run_loop_continue.sh)):
- **Generator:** if a second quantity follows the leading one, do not scale the line; report it in `unscaled`. Use one general rule instead of more regexes, and document the limitations.
- **Critic** ([`critic-acceptance.txt`](agent-logs/loop/critic-acceptance.txt)): a line that is left unchanged, reported in `unscaled`, and documented is an accepted limitation. Correctness FAIL is only for a *silently* wrong result.

In round 6 the generator replaced 8 special-case regexes with one rule. The critic accepted the reported limitations, but still found a silently wrong case: amounts that are not at the start of the line (`"flour 200 g"`). Under my acceptance criterion this was a valid FAIL.

### How it ended – the critic did not sign off
- **Round 7 hit the Claude usage limit.** The generator stopped after a partial edit, and the critic returned no verdict (`"You've hit your 5-hour limit"`, see `round7-*.jsonl`). The loop script committed that partial edit.
- **I removed it from the delivered code.** The scaling branch was reset to round 6, and the partial commit is kept for transparency on branch [`task-c/round7-partial-unreviewed`](https://github.com/Ezzgiturann/week7-recipe-box/tree/task-c/round7-partial-unreviewed). An earlier attempt to revert it with `git revert -q` failed silently, because `revert` has no `-q` option. The `--amend` that followed then reworded the partial commit instead of reverting it. I caught this before merging, by checking the diff against round 6.
- **The merged code is round 6:** 133 scaling tests, 150 in total after the merge. **The critic never gave `APPROVE`.** The open finding is that amounts not at the start of a line (`"flour 200 g"`, `"Eggs: 2"`, `"about 2 cups"`) are not scaled and not reported in `unscaled`.
- **Merging this branch hit the same collision as Part I.** The generator was a third agent unaware of the others, and it also wrote an autouse fixture named `temp_db`. It had also moved `get_recipe`'s body into `_fetch_recipe`, at the exact spot where agent A had added the shopping list. I resolved both in [`29eac97`](https://github.com/Ezzgiturann/week7-recipe-box/commit/29eac97).

## 3. Autonomy levels and supervision

| Agent | Allowed tools | Not allowed | Session |
|---|---|---|---|
| A, B (Part I) | Read, Edit, Write, Glob, Grep, `pytest*`, `python*` | git, other shell commands, network | one-shot |
| Generator (Part II) | Read, Edit, Write, Glob, Grep, `pytest*`, `python*` | git, other shell commands, network | one session, resumed every round (`--resume`) so it remembers its earlier decisions |
| Critic (Part II) | Read, Glob, Grep, `git diff*`, `git log*`, `pytest*` | **any file edit**, `python` | a **fresh** session every round, so it does not defend its earlier verdicts |

- **Edits were automatic, integration was not.** The agents could edit files without asking (`--permission-mode acceptEdits`). Commits, merges and conflict resolution stayed with me.
- **The allowlist was enforced by the tool, not by trust.** The generator tried `python --version && sed -i ... main.py`, and Claude Code refused it, because it checks each command in a `&&` chain separately. "Do not commit" in the prompt was backed by git not being on the list.
- **Supervision mistake: my critic allowlist was too narrow.** The round-1 critic tried `python -m pytest`, which did not match `pytest*`, so it could not run the tests and said so in its report. The round-2 critic used `pytest -q` and ran them (72 passed). Restricting autonomy has a cost: the round-1 review was a static read of the code.
- **How I supervised:**
  - I read every agent's summary and tool log, and ran `pytest` myself on every branch before committing.
  - I tested the merged app with `curl`.
  - I proved the naive merge resolution wrong with a probe test.
  - I committed every generator round separately, so the loop is visible in git history.

## 4. What I learned

<!-- Student's own words (course rule: no AI-written reflections). -->

İki agent aynı anda çalışırken aynı isimde dosya veya fixture oluşturabileceklerini ve Git conflict'inin çözülmesinin her zaman doğru sonucu garanti etmediğini öğrendim.

Kodu yazan agent kendi yaptığı testlere odaklanırken, ayrı bir critic farklı açılardan bakarak testlerde fark edilmeyen hataları bulabildiği için iki agent kullanmanın faydalı olduğunu gördüm.

Bir sonraki çalışmamda agent'ların görevlerine uygun izinler verirdim. Kod yazan agent'ın gereksiz dosya değişikliklerini sınırlar, critic'in ise testleri çalıştırabilmesi için gerekli komutlara izin verirdim.
