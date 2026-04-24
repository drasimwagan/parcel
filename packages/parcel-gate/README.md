# parcel-gate

Static-analysis gate for Parcel modules. Runs `ruff` + `bandit` + a custom AST
policy against a candidate module directory and returns a structured
`GateReport`. Used by the sandbox-install pipeline in `parcel-shell` to decide
whether a candidate is safe to install.
