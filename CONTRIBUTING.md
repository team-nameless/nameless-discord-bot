# Contribution Guides

> Not exhaustive, but it should be practical.

- First of all, install development dependencies:

```shell
pip install requirements_dev.txt
```

- Coding conventions:
	- We follow PEP8 rule, with a small modification:
		- Use 120 characters limit instead of 88.
	- We follow `black` code style.
		- Be sure to format the document with `black` before commiting:

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

- Commiting conventions:
	- Under consideration, some initial rules:
		- Use present tense.
		- Make the commit readable.
		- No-code changes should be prefixed with `[ci skip]`
		- Branch naming:
			- Use `feat/{name}` if you want to add a feature.
			- Use `fix/{name}` or `fix/{#}` if you want to fix a bug in it.
