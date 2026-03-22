# Add linters and other static code analysers

## Why

- Codebase has a lot of dead code, unused variables and imports
- Many files have indentattion or formatting issues

## Wants

- Delete the bart-large-mnli-onnx model and its related codes, since its no longer used.
- Add best linters for all languages used in this project, like python, javascript, html, css and others
- Add best and free static code analyser that will analyse both frontend and backend code
- Add them to the package manager and to our start scripts so that we always ensure we are running linted, properly formatted code
- Take outputs from the linters and static code analyser tools and work on it to fix the issues. Remove all dead code, unused variables and imports.
- Must not break any backend or frontend functionality or feature
- Must not make any visual changes
- Look for code smells, anti-patterns. Static code analysers tool will tell you all this.
- Don't assume on your own. Remember you are not deterministic. So take help from tools those are deterministic and will help me to reorganise my entire codebase.
- For example, routes.py has a lot of methods those do utils/helpers task. Move them out to suitable classes or files. routes.py should only have the routes.
- Make code readable and focus a lot of maintainibilty
- Follow engineering best practices
- Write meaningful log statements. Expose no PIIs in production logs. Debug logs can have user info and other data.
- Keep methods small. Make code modular.
- Follow Martin's clean code principles


## Validation

- Run all tests
- Fix all failing tests
- Break no existing functionality
