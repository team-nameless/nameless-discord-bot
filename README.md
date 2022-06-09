# nameless

A rewrite of [original nameless*](https://github.com/FoxeiZ/nameless), now with collaborations.

[![Last Commit](https://badgen.net/github/last-commit/nameless-on-discord/nameless/main)]()
[![Python](https://badgen.net/badge/Python/3.8%2B/)]()
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

[![CodeFactor](https://www.codefactor.io/repository/github/nameless-on-discord/nameless/badge/main)](https://www.codefactor.io/repository/github/nameless-on-discord/nameless/overview/main)
[![Total alerts](https://img.shields.io/lgtm/alerts/g/Lilia-Workshop/nameless.svg?logo=lgtm&logoWidth=18)](https://lgtm.com/projects/g/nameless-on-discord/nameless/alerts/)
[![Language grade: Python](https://img.shields.io/lgtm/grade/python/g/Lilia-Workshop/nameless.svg?logo=lgtm&logoWidth=18)]()
[![anything-python](https://badgen.net/github/checks/nameless-on-discord/nameless/main?label=Continuous%20Ingerations&icon=github)]()

----------------------------------------

## How to run this bot?

- First, install `python3` or `pypy`, latest version preferred.
- Second, create a virtual environment so your global "python" won't be badly affected and activate it (most IDEs
  automatically activate it for you)

```shell
# Replace python3 with pypy if you are going to use pypy
python3 -m venv venv
source venv/bin/activate
```

- Third, install required dependencies:

```shell
pip install -r requirements_core.txt
```

- After that, edit `config.example.py` then rename to `config.py`.

- Lastly, run the `main.py` file:

```shell
python main.py
```

- In case you encounter the `Target database is not up to date` problem:

```shell
alembic stamp head
```

## Noice, your code is so cool, and I wanna contribute my parts on them

See [CONTRIBUTING.md](https://github.com/Lilia-Workshop/nameless/blob/main/CONTRIBUTING.md)

## Oh look, there are branches

- `main`: Stable codes that is ready for production.
- `feat/{name}`: New features that will be pushed to `main`
- `fix/{#}` or `fix/{name}`: Bug fixes that will be pushed after passing checks.

## Hey! I want to throw money at you

- Oh, thank you for your generosity! You can look for the sponsor button or some link at the sidebar, any value is
  appreciated.

----------------------------------------

## The team

- Me, of course, lol.
- [FoxeiZ](https://github.com/FoxeiZ)
