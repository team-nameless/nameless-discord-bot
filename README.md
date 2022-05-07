# nameless

A rewrite of [original nameless*](https://github.com/FoxeiZ/nameless)

[![CodeFactor](https://www.codefactor.io/repository/github/lilia-workshop/nameless/badge/main)](https://www.codefactor.io/repository/github/lilia-workshop/nameless/overview/main)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Python](https://badgen.net/badge/Python/3.10/)](https://python.org/)

----------------------------------------

## How to run this bot?

- First, install `python3`, latest version preferred.
- Second, create a virtual environment so your global `python3` won't be badly affected and activate it (most IDEs
  automatically activate it for you)

```shell
python3 -m venv venv
source venv/bin/activate
```

- Third, install required dependencies:

```shell
pip install -r requirements_core.txt
```

- After that, create a config file naming `config.py`
  and [fill it](https://github.com/Lilia-Workshop/nameless/wiki/config.py).
  Also [setup your database](https://github.com/Lilia-Workshop/nameless/wiki/Setup-database-(PostgreSQL)) (PostgreSQL
  for example, YMMV. We also support MongoDB/MongoDB Atlas).

- Lastly, run the `main.py` file:

```shell
python3 main.py
```

## Noice, your code is so cool, and I wanna contribute my parts on them!

See [CONTRIBUTING.md](https://github.com/Lilia-Workshop/nameless/blob/main/CONTRIBUTING.md)

## Oh look, there are branches!

- `main`: Stable codes that is ready for production.
- `dev`: Changes that might not backward-compatible with `main`, and will be pushed to production at a later time after
  careful testing and reviewing.
- `feat/{name}`: New features that will be pushed to `dev`
- `fix/{#}` or `fix/{name}`: Bug fixes that will be pushed to EITHER `main` OR `dev`, depending on its severity.

## Hey! I wanna throw money at you!

- Oh, thank you for your generosity! You can look for the sponsor button or some link at the sidebar, any value is
  appreciated.

----------------------------------------

## Credits (click on them to get to their GitHub profile)

![Me](https://img.shields.io/badge/%E2%9D%A4%EF%B8%8FMade%20with%20love%20by-Swyrin%237193-red?style=for-the-badge&logo=discord)
[![Python God](https://img.shields.io/badge/Python%20God-C%C3%A1o%20trong%20s%C3%A1ng%238029-blue?style=for-the-badge&logo=python)](https://github.com/FoxeiZ)