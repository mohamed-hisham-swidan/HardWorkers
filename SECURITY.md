# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 3.x     | :white_check_mark: |

## Reporting a Vulnerability

We take security seriously. If you discover a security vulnerability, please report it privately.

**Do NOT** report security issues via the public issue tracker.

Send details to the project maintainers via a private channel or email.

Please include:

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

We will acknowledge receipt within 48 hours and provide a timeline for a fix.

## Security Best Practices

- Never commit `.env` files or API keys to version control
- Change default credentials (`admin`/`admin`) in production
- Set a strong `JWT_SECRET` in production environments
- Use the provided `.env.example` as a template — never fill secrets into it
- Keep dependencies updated via `pip-audit` or `dependabot`
- Run the application behind a reverse proxy (e.g., nginx) when exposed to a network
