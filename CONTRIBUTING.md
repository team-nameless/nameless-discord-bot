# Contribution Guides

> Not exhaustive, but it should be practical.

- First of all, install development dependencies:

```shell
pip install -U -r requirements_dev.txt
```

- Coding conventions:
    - We follow PEP8 rule from `pycodestyle`, with a small modification:
        - Use 120 characters limit instead of 88.
    - We follow `black` code style.
        - Be sure to format the document with `black` before committing:

   ```shell
   black .
   ```

    - When making commands:
        - We expect that the function's name should be the command's name.
            - Exceptions:
                - You have a better name for it.
                - Context menu commands: We use `{message/user}_context_menu_{command_name}` for that
        - We expect that the function parameter's name should be the command parameter's name.
            - Exceptions:
                - You have a better name for it.

- Committing conventions:
    - Use present tense.
    - Make the commit message understandable.
        - Each commit message should correspond to the code changes.
    - No-code changes should be prefixed with `[ci skip]` and pushed to `main`
    - Branch naming:
        - Use `feat/{name}` for a feature.
        - Use `fix/{name}` or `fix/{#issue/#pr}` for bug fixtures.

- Database contribution guides:
    - We follow PascalCase SQLAlchemy name override convention.
    - Every column edits
        - Must include the property in constructor:

          ```python
          def __init__(self, anything_else, your_new_field):
            self.your_new_field = your_new_field
          ```

        - Must include the change in both `from_dict` and `to_dict`:
          ```python
          def from_dict(self, d: dict):
            self.your_new_field = d["your_new_field"]
          
          def to_dict(self):
            return {
               "your_new_field": self.your_new_field
            }
          ```

        - Must be committed to `alembic` by using:

          ```shell
          alembic revision --autogenerate -m "Message here"
          alembic upgrade head
          ```
          
          - If you are experiencing `Target database is not up to date`, run `alembic stamp head` first. 
  
    