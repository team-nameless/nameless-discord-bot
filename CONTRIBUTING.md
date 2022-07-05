# Contribution Guides

> Not exhaustive, but it should be practical.

- First:
  - Install/upgrade development dependencies:

  ```shell
  pip install --upgrade -r requirements_dev.txt
  ```
  
  - Install `pre-commit` hooks if you have not.
  
  ```shell
  pre-commit install
  ```

- Coding conventions:
  - We follow `flake8` and `pylint` rule.
  - We follow `black` code style.
    - Be sure to format the document with `black` and `isort` before committing:

   ```shell
   isort .
   black .
   ```

  - When creating commands:
    - We expect that the function's name should be the command's name.
      - Exceptions:
        - Context menu commands: We use `{message/user}_context_menu_{command_name}` for that
    - We expect that the function parameter's name should be the command parameter's name.

- Committing conventions:
  - Use present tense, or at least understandable by humans.
    - Each commit message should correspond to the code changes.
      - Not necessary in near future, will enforce later
  - No-code changes should be prefixed with `[ci skip]`
  - Branch naming:
    - Use `feat/{name}` for a feature.
    - Use `fix/{name}` or `fix/{#}` for bug fixtures.

- Database contribution guides:
  - We use PascalCase for column naming (`name` keyword arg) and snake_case for class prop naming.
  - Every column edits:
    - Must add a property in class body (remember to type it):

      ```python
      class ACoolClass(Base):
        ...
        your_new_field: Type = Column(..., name="YourNewField")
      ```

    - Must be included in `__init__()` with the field name prefixed with `_` and a default value.

      ```python
      def __init__(..., _your_new_field: str = "wah"):
        ...
        self.your_new_field = _your_new_field
      ```

    - Must be committed to `alembic` by using (ONE CHANGE ONLY):

      ```shell
      alembic revision --autogenerate -m "Message here"
      alembic upgrade head
      ```
