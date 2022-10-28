# nameless

A rewrite of [original nameless*](https://github.com/FoxeiZ/nameless), now with collaborations.

[![Last Commit](https://badgen.net/github/last-commit/nameless-on-discord/nameless/main)]()
[![Python](https://badgen.net/badge/Python/3.10%2B/)](https://python.org)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Latest tag](https://badgen.net/github/tag/nameless-on-discord/nameless?label=Latest%20Stable%20Version)]()

[![CodeFactor](https://www.codefactor.io/repository/github/nameless-on-discord/nameless/badge/main)](https://www.codefactor.io/repository/github/nameless-on-discord/nameless/overview/main)
[![Total alerts](https://img.shields.io/lgtm/alerts/g/Lilia-Workshop/nameless.svg?logo=lgtm&logoWidth=18)](https://lgtm.com/projects/g/nameless-on-discord/nameless/alerts/)
[![Language grade: Python](https://img.shields.io/lgtm/grade/python/g/Lilia-Workshop/nameless.svg?logo=lgtm&logoWidth=18)]()

----------------------------------------

## CI Status
 
[![MAIN CI](https://badgen.net/github/checks/nameless-on-discord/nameless/main?label=main&icon=github)]()

----------------------------------------

## How to run this bot?

- First, install `python3` - minimum version `3.10`, latest version preferred.
- Second, create a virtual environment so your global `python` won't be badly polluted by packages and activate it.

```shell
python3 -m venv venv
source venv/bin/activate
```

- Third, install required dependencies:

```shell
pip install -r requirements_core.txt
```

- After that, edit `NamelessConfig_example.py` then rename to `NamelessConfig.py`.

- Lastly, run the `main.py` file:

> :warning: Update checks are disabled by default, if you want to enable it, use flag `--allow-updates-check`

```shell
python main.py -OO
```

> In case you encounter the `Target database is not up to date` problem:

```shell
alembic stamp head
```

## Noice, your code is so cool, and I want to contribute!

See [CONTRIBUTING.md](https://github.com/Lilia-Workshop/nameless/blob/main/CONTRIBUTING.md)

## Oh look, there are branches!

- [main](https://github.com/nameless-on-discord/nameless/tree/main): Stable codes that is production-ready.
- `feat/{name}`: New features that will be pushed directly or through PRs to `main`
- `fix/{#}` or `fix/{name}`: Bug fixes that will be pushed to `main` after passing checks.

## Hey! I want to throw money at you!

- Oh, thank you for your generosity! You can look for the sponsor button or some link at the sidebar, any value is
  appreciated.

----------------------------------------

## The team

- [Swyrin](https://github.com/Swyreee)
- [FoxeiZ](https://github.com/FoxeiZ)
- And [all the contributors](https://github.com/nameless-on-discord/nameless/graphs/contributors)
