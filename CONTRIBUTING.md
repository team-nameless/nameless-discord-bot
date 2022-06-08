# Contribution Guides

> Not exhaustive, but it should be practical.

- First of all, install development dependencies:

```shell
pip install -U -r requirements_dev.txt
```

- Coding conventions:
    - We follow PEP8 rule from `pycodestyle`
    - We follow `black` code style.
        - Be sure to format the document with `black` before committing:

   ```shell
   black .
   ```

    - When making commands:
        - We expect that the function's name should be the command's name.
            - Exceptions:
                - Context menu commands: We use `{message/user}_context_menu_{command_name}` for that
        - We expect that the function parameter's name should be the command parameter's name.

- Committing conventions:
    - Use present tense.
    - Make the commit message understandable.
        - Each commit message should correspond to the code changes.
    - No-code changes should be prefixed with `[ci skip]` and pushed to `main`
    - Branch naming:
        - Use `feat/{name}` for a feature.
        - Use `fix/{name}` or `fix/{#}` for bug fixtures.

- Database contribution guides:
    - We use PascalCase for column naming.
    - Every column edits
        - Must add a property in class body (remember to type it):

          ```python
          class ACoolClass(Base):
            ...
            your_new_field = Column(..., name="YourNewField")
          ```
          
        - Must be included in `__init__()` with the field name prefixed with `_` and a default value.
          ```python
          def __init__(..., _your_new_field: str = "wah"):
            ...
            self.your_new_field = _your_new_field
          ```

        - Must be committed to `alembic` by using:

          ```shell
          alembic revision --autogenerate -m "Message here"
          alembic upgrade head
          ```
