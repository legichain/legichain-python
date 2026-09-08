# SDK continuous integration

Forgejo Actions runs this repository's tests on pushes to main and pull requests,
on the isolated `lc-sdk` runner. Application deployments do not depend on this
workflow. GitHub remains a Git mirror with Actions disabled.

The V2 client changes are tested here without changing existing V1 methods.
CI builds/checks packages locally; publishing a package registry version is a
separate release action. Package versions and existing release history are retained.

SDK code changes belong in this repository. The application repository's old
`sdk/` directory is a historical source snapshot, not an automatic release source.
