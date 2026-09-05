"""Constants for the Pluxee integration."""

from datetime import timedelta

DOMAIN = "pluxee"
PLATFORM = "sensor"

ATTRIBUTION = "Data provided by Pluxee"

DEFAULT_ICON = "mdi:credit-card"

# Pluxee Portal URLs
API_LOGIN_URL = "https://portal.admin.pluxee.pt/"
API_CONSUMER_URL = "https://consumidores.pluxee.pt/"

# Field name for NIF (tax identification number)
CONF_NIF = "nif"

CONF_USER_AGENT_TOKEN = "user_agent_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_TOKEN_EXPIRES_AT = "token_expires_at"

UPDATE_INTERVAL = timedelta(minutes=30)

# Maximum number of transactions to fetch and expose
DEFAULT_TRANSACTIONS_COUNT = 20

# Service names
SERVICE_REFRESH = "refresh"
