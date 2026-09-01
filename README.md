# Pluxee Benefits Integration for Home Assistant

Custom component for Home Assistant to integrate Pluxee benefits cards.

## 🚧 Work in Progress

This integration is currently under development. The authentication flow and API client are being implemented.

## Features (Planned)

- 🔐 Authentication with Pluxee portal
- 💳 Monitor card balance
- 📊 Track transaction history
- 🔄 Automatic data refresh
- 🌍 Multi-language support (EN, PT)

## Installation

### Development Setup

1. Clone this repository
2. Copy `.env` and configure your credentials
3. Build and run the Docker container:

```bash
docker-compose up -d
```

4. Access Home Assistant at http://localhost:8124
5. Add the Pluxee integration through the UI

## Configuration

The integration uses a config flow for setup:

1. Go to Settings → Devices & Services
2. Click "+ Add Integration"
3. Search for "Pluxee"
4. Enter your Pluxee portal credentials
5. Complete 2FA verification if required

## Development Status

### ✅ Completed

- Basic project structure
- Config flow skeleton
- Docker development environment
- Translations (EN, PT)

### 🚧 In Progress

- API client implementation
- Authentication flow
- Data coordinator

### 📋 TODO

- Sensor entities
- Service implementation
- Testing
- Documentation

## Contributing

This is a personal project, but suggestions and bug reports are welcome through GitHub issues.

## License

See [LICENSE](LICENSE) file.

## Disclaimer

This is an unofficial integration and is not affiliated with or endorsed by Pluxee.
