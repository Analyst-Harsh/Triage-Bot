# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/Analyst-Harsh/Triage-Bot/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                  |    Stmts |     Miss |   Cover |   Missing |
|-------------------------------------- | -------: | -------: | ------: | --------: |
| api/\_\_init\_\_.py                   |        0 |        0 |    100% |           |
| api/github\_client.py                 |       39 |        0 |    100% |           |
| config/\_\_init\_\_.py                |        2 |        0 |    100% |           |
| config/settings.py                    |       29 |        0 |    100% |           |
| graph/\_\_init\_\_.py                 |        0 |        0 |    100% |           |
| graph/builder.py                      |       38 |        0 |    100% |           |
| graph/checkpointer.py                 |       15 |        0 |    100% |           |
| graph/nodes/\_\_init\_\_.py           |       11 |        0 |    100% |           |
| graph/nodes/agent\_subgraph.py        |       81 |        8 |     90% |122-126, 134, 144, 169 |
| graph/nodes/approval\_queue.py        |        9 |        0 |    100% |           |
| graph/nodes/auto\_post.py             |       29 |        1 |     97% |        25 |
| graph/nodes/base.py                   |       23 |        1 |     96% |        68 |
| graph/nodes/drafter.py                |       77 |        3 |     96% |99-100, 268 |
| graph/nodes/llm\_node.py              |       18 |        3 |     83% |     36-38 |
| graph/nodes/node\_names.py            |        8 |        0 |    100% |           |
| graph/nodes/planner.py                |       19 |        0 |    100% |           |
| graph/nodes/researcher.py             |       38 |        0 |    100% |           |
| graph/nodes/risk\_check.py            |       48 |        1 |     98% |        47 |
| graph/nodes/trajectory.py             |       59 |        0 |    100% |           |
| graph/nodes/utils/\_\_init\_\_.py     |        0 |        0 |    100% |           |
| graph/nodes/utils/action\_executor.py |       31 |        1 |     97% |        30 |
| graph/schemas/\_\_init\_\_.py         |       13 |        0 |    100% |           |
| graph/schemas/actions.py              |       20 |        0 |    100% |           |
| graph/schemas/draft.py                |       12 |        0 |    100% |           |
| graph/schemas/enums.py                |       37 |        0 |    100% |           |
| graph/schemas/grounding.py            |        3 |        0 |    100% |           |
| graph/schemas/issue.py                |        7 |        0 |    100% |           |
| graph/schemas/memory.py               |        5 |        0 |    100% |           |
| graph/schemas/planner.py              |       10 |        0 |    100% |           |
| graph/schemas/post\_result.py         |        7 |        0 |    100% |           |
| graph/schemas/research.py             |       23 |        0 |    100% |           |
| graph/schemas/risk.py                 |       12 |        0 |    100% |           |
| graph/schemas/run\_meta.py            |       13 |        0 |    100% |           |
| graph/schemas/sandbox.py              |        5 |        0 |    100% |           |
| graph/state.py                        |        9 |        0 |    100% |           |
| llm/\_\_init\_\_.py                   |        6 |        0 |    100% |           |
| llm/config.py                         |        5 |        0 |    100% |           |
| llm/factory.py                        |       11 |        0 |    100% |           |
| llm/pricing.py                        |       10 |        0 |    100% |           |
| llm/result.py                         |        3 |        0 |    100% |           |
| llm/structured.py                     |       36 |        1 |     97% |        80 |
| observability/\_\_init\_\_.py         |        0 |        0 |    100% |           |
| observability/logging\_config.py      |       21 |        0 |    100% |           |
| prompts/\_\_init\_\_.py               |        2 |        0 |    100% |           |
| prompts/drafter.py                    |       80 |        0 |    100% |           |
| prompts/planner.py                    |        7 |        0 |    100% |           |
| prompts/researcher.py                 |       11 |        0 |    100% |           |
| prompts/risk\_check.py                |       17 |        0 |    100% |           |
| tools/\_\_init\_\_.py                 |        0 |        0 |    100% |           |
| tools/mcp\_clients.py                 |       50 |        9 |     82% |   102-110 |
| tools/sandbox.py                      |      396 |       17 |     96% |111-112, 114, 204, 438, 483-485, 509-510, 634-641, 961, 964, 967, 972, 975 |
| **TOTAL**                             | **1405** |   **45** | **97%** |           |


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