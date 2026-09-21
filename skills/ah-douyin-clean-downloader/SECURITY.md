# Security policy

## Supported release

Security fixes are applied to the latest published release only.

## Report privately

Do not place private share links, cookies, tokens, proxy credentials, downloaded
videos, or personal information in a public issue. Contact the repository owner
through a private channel listed on the repository and include:

- affected version or commit;
- operating system and Python version;
- a minimal reproduction using a redacted or synthetic link;
- expected and observed behavior;
- whether the issue could expose local files, credentials, or private network
  resources.

## Security boundaries

- The downloader accepts only official Douyin-family share hosts.
- Redirect results and media URLs are validated before use.
- Localhost and literal private-network media addresses are rejected.
- Existing output files are not overwritten.
- Partial files are used while downloading.
- The program does not persist cookies, account credentials, or tokens.

This tool cannot guarantee that a remote platform endpoint is always available,
safe, or unchanged. Review changes before running them on sensitive systems.
