# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/Analyst-Harsh/Triage-Bot/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                             |    Stmts |     Miss |   Cover |   Missing |
|------------------------------------------------- | -------: | -------: | ------: | --------: |
| api/\_\_init\_\_.py                              |        0 |        0 |    100% |           |
| api/app.py                                       |       39 |        0 |    100% |           |
| api/dependencies.py                              |       30 |        1 |     97% |        61 |
| api/errors.py                                    |        6 |        0 |    100% |           |
| api/routers/\_\_init\_\_.py                      |        0 |        0 |    100% |           |
| api/routers/runs.py                              |       79 |        2 |     97% |   116-117 |
| api/routers/runs\_collection.py                  |       12 |        0 |    100% |           |
| api/routers/webhooks.py                          |       41 |        0 |    100% |           |
| api/schemas/\_\_init\_\_.py                      |       10 |        0 |    100% |           |
| api/schemas/detail\_response.py                  |        2 |        0 |    100% |           |
| api/schemas/error\_detail.py                     |        5 |        0 |    100% |           |
| api/schemas/github\_webhook.py                   |       15 |        0 |    100% |           |
| api/schemas/retry\_request.py                    |        3 |        0 |    100% |           |
| api/schemas/run\_accepted\_response.py           |        5 |        0 |    100% |           |
| api/schemas/run\_detail\_response.py             |        4 |        0 |    100% |           |
| api/schemas/run\_list\_response.py               |        3 |        0 |    100% |           |
| api/schemas/run\_summary.py                      |       27 |        0 |    100% |           |
| api/schemas/run\_summary\_response.py            |        3 |        0 |    100% |           |
| config/\_\_init\_\_.py                           |        2 |        0 |    100% |           |
| config/guardrail\_settings.py                    |       20 |        0 |    100% |           |
| config/settings.py                               |       35 |        0 |    100% |           |
| db/\_\_init\_\_.py                               |        2 |        0 |    100% |           |
| db/engine.py                                     |       16 |        0 |    100% |           |
| graph/\_\_init\_\_.py                            |        0 |        0 |    100% |           |
| graph/builder.py                                 |       43 |        0 |    100% |           |
| graph/checkpointer.py                            |       24 |        0 |    100% |           |
| graph/errors.py                                  |        8 |        0 |    100% |           |
| graph/nodes/\_\_init\_\_.py                      |       13 |        0 |    100% |           |
| graph/nodes/agent\_subgraph.py                   |       98 |       10 |     90% |141-147, 155, 165, 190 |
| graph/nodes/approval\_queue.py                   |       62 |        1 |     98% |       118 |
| graph/nodes/auto\_post.py                        |       43 |        3 |     93% | 39-40, 95 |
| graph/nodes/base.py                              |       30 |        1 |     97% |       104 |
| graph/nodes/drafter.py                           |       78 |        3 |     96% |96-97, 277 |
| graph/nodes/llm\_node.py                         |       19 |        4 |     79% |     36-39 |
| graph/nodes/node\_names.py                       |        9 |        0 |    100% |           |
| graph/nodes/planner.py                           |       27 |        2 |     93% |     33-34 |
| graph/nodes/researcher.py                        |       41 |        1 |     98% |        50 |
| graph/nodes/risk\_check.py                       |       78 |        5 |     94% |36-37, 65-66, 71 |
| graph/nodes/routing.py                           |       18 |        0 |    100% |           |
| graph/nodes/spam\_close.py                       |       21 |        0 |    100% |           |
| graph/nodes/trajectory.py                        |       73 |        0 |    100% |           |
| graph/nodes/utils/\_\_init\_\_.py                |        0 |        0 |    100% |           |
| graph/nodes/utils/action\_executor.py            |       46 |        1 |     98% |       128 |
| graph/nodes/utils/approval\_request\_builder.py  |       41 |        0 |    100% |           |
| graph/nodes/utils/budget\_guard.py               |        7 |        0 |    100% |           |
| graph/nodes/utils/budget\_guard\_middleware.py   |       19 |        0 |    100% |           |
| graph/nodes/utils/episodic\_memory\_gateway.py   |       21 |        0 |    100% |           |
| graph/nodes/utils/injection\_pattern\_scanner.py |       32 |        1 |     97% |       118 |
| graph/schemas/\_\_init\_\_.py                    |       16 |        0 |    100% |           |
| graph/schemas/actions.py                         |       20 |        0 |    100% |           |
| graph/schemas/approval\_decision.py              |        7 |        0 |    100% |           |
| graph/schemas/approval\_request.py               |       17 |        0 |    100% |           |
| graph/schemas/base.py                            |        3 |        0 |    100% |           |
| graph/schemas/draft.py                           |       13 |        0 |    100% |           |
| graph/schemas/enums.py                           |       45 |        0 |    100% |           |
| graph/schemas/episode.py                         |        9 |        0 |    100% |           |
| graph/schemas/grounding.py                       |        4 |        0 |    100% |           |
| graph/schemas/issue.py                           |        8 |        0 |    100% |           |
| graph/schemas/memory.py                          |        7 |        0 |    100% |           |
| graph/schemas/planner.py                         |       11 |        0 |    100% |           |
| graph/schemas/post\_result.py                    |        8 |        0 |    100% |           |
| graph/schemas/research.py                        |       25 |        0 |    100% |           |
| graph/schemas/risk.py                            |       15 |        0 |    100% |           |
| graph/schemas/run\_meta.py                       |       18 |        0 |    100% |           |
| graph/schemas/sandbox.py                         |        5 |        0 |    100% |           |
| graph/state.py                                   |       11 |        0 |    100% |           |
| llm/\_\_init\_\_.py                              |        6 |        0 |    100% |           |
| llm/config.py                                    |        5 |        0 |    100% |           |
| llm/factory.py                                   |       11 |        0 |    100% |           |
| llm/pricing.py                                   |       14 |        0 |    100% |           |
| llm/result.py                                    |        5 |        0 |    100% |           |
| llm/structured.py                                |       42 |        1 |     98% |        67 |
| main.py                                          |       85 |       32 |     62% |52-55, 70-76, 126-215, 224 |
| models/\_\_init\_\_.py                           |        2 |        0 |    100% |           |
| models/base.py                                   |        2 |        0 |    100% |           |
| models/triage\_run.py                            |       12 |        0 |    100% |           |
| observability/\_\_init\_\_.py                    |        0 |        0 |    100% |           |
| observability/logging\_config.py                 |       21 |        0 |    100% |           |
| observability/tracing.py                         |       38 |        7 |     82% |154-168, 189-190 |
| prompts/\_\_init\_\_.py                          |        2 |        0 |    100% |           |
| prompts/drafter.py                               |       80 |        0 |    100% |           |
| prompts/planner.py                               |       15 |        0 |    100% |           |
| prompts/researcher.py                            |       11 |        0 |    100% |           |
| prompts/risk\_check.py                           |       17 |        0 |    100% |           |
| repositories/\_\_init\_\_.py                     |        2 |        0 |    100% |           |
| repositories/triage\_run\_repository.py          |       91 |        0 |    100% |           |
| services/\_\_init\_\_.py                         |        3 |        0 |    100% |           |
| services/errors.py                               |       51 |        0 |    100% |           |
| services/triage\_run\_record.py                  |        7 |        0 |    100% |           |
| services/triage\_run\_service.py                 |      144 |        3 |     98% |261, 273-278 |
| tools/\_\_init\_\_.py                            |        0 |        0 |    100% |           |
| tools/mcp\_clients.py                            |       50 |        9 |     82% |   102-110 |
| tools/sandbox.py                                 |      393 |       17 |     96% |110-111, 113, 203, 439, 484-486, 510-511, 635-642, 971, 974, 977, 982, 985 |
| utils/\_\_init\_\_.py                            |        0 |        0 |    100% |           |
| utils/diff\_applier.py                           |      105 |        8 |     92% |35, 51, 67-68, 90, 96, 116, 200 |
| utils/episodic\_memory\_store.py                 |       68 |       10 |     85% |68, 82, 230-248 |
| utils/github\_client.py                          |       71 |        1 |     99% |       148 |
| utils/postgres\_pool.py                          |       12 |        0 |    100% |           |
| **TOTAL**                                        | **2817** |  **123** | **96%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/Analyst-Harsh/Triage-Bot/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/Analyst-Harsh/Triage-Bot/blob/python-coverage-comment-action-data/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/Analyst-Harsh/Triage-Bot/python-coverage-comment-action-data/endpoint.json)](https://htmlpreview.github.io/?https://github.com/Analyst-Harsh/Triage-Bot/blob/python-coverage-comment-action-data/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2FAnalyst-Harsh%2FTriage-Bot%2Fpython-coverage-comment-action-data%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/Analyst-Harsh/Triage-Bot/blob/python-coverage-comment-action-data/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.