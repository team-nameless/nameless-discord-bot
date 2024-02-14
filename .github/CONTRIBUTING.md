# Contribution Guides

> Not exhaustive, but it should be practical.

## Install development dependencies.

  ```shell
  pip install --upgrade -r requirements_dev.txt
  ```

### Conventions for nameless*
- We use **4 spaces**.
- When creating commands:
  - The function's name should be the command's name.
  - The function parameters' name should be the command parameter's name.

- Committing conventions:
  - Use present tense, or at least understandable by humans.
    - Each commit message should correspond to the code changes.
      - Not necessary in near future, will enforce later.
  - No-code changes should be prefixed with `[ci skip]`
  - Branch naming:
    - Use `feat/{name}` for a feature.
    - Use `fix/{name}` or `fix/{#}` for bug fixtures.

### Conventions for database
- We use `snake_case` for model class properties naming.
- Every column additions:
  - Must add a property in class body (remember to type it):

    ```python
    class ACoolClass(Base):
      ...
      your_new_field: Type = Column(...)
    ```

  - Must be included in `__init__()` with the field name prefixed with `_` and a default value.

    ```python
    def __init__(..., _your_new_field: str = "wah"):
      ...
      self.your_new_field = _your_new_field
    ```

  - Must be committed to `alembic`:

    ```shell
    alembic revision --autogenerate -m "Message here"
    alembic upgrade head
    ```
