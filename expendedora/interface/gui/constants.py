"""Constantes de la capa interfaz."""

GUI_FOOTER_HEIGHT = 44
PROMO_DEBOUNCE_S = 0.85

DEFAULT_PROMO_HOTKEYS = {
    "Promo 1": ["<slash>", "<KP_Divide>"],
    "Promo 2": ["<asterisk>", "<KP_Multiply>", "x", "X"],
    "Promo 3": ["<minus>", "<KP_Subtract>"],
}

PROMO_CONTADOR_KEYS = {
    "Promo 1": "promo1_contador",
    "Promo 2": "promo2_contador",
    "Promo 3": "promo3_contador",
}

URL_CIERRES_LOCAL = "AdministrationPanel/src/expendedora/insert_close_expendedora.php"
URL_CIERRES_CLOUD = "src/expendedora/insert_close_expendedora.php"
URL_SUBCIERRE_LOCAL = "AdministrationPanel/src/expendedora/insert_subcierre_expendedora.php"
URL_SUBCIERRE_CLOUD = "src/expendedora/insert_subcierre_expendedora.php"
DNS = "https://app.maquinasbonus.com/"
DNS_LOCAL = "http://127.0.0.1/"
