"""
Módulo de buffer compartido entre GUI y Core.
Contiene colas para comunicación asíncrona y datos compartidos con locks para thread-safety.
"""

from queue import Queue
import threading

# Cola para comandos desde GUI hacia Core
gui_to_core_queue = Queue()

# Datos compartidos con lock para thread-safety
shared_data_lock = threading.Lock()
shared_data = {
    'fichas_restantes': 0,
    'fichas_expendidas': 0,
    'cuenta': 0,
    'r_cuenta': 0,
    'r_sal': 0,
    'promo1_count': 0,
    'promo2_count': 0,
    'promo3_count': 0,
    'motor_activo': False
}

# Funciones thread-safe para acceder a datos compartidos
def get_fichas_restantes():
    with shared_data_lock:
        return shared_data['fichas_restantes']

def get_fichas_expendidas():
    with shared_data_lock:
        return shared_data['fichas_expendidas']

def set_fichas_restantes(value):
    with shared_data_lock:
        shared_data['fichas_restantes'] = value

def set_fichas_expendidas(value):
    with shared_data_lock:
        shared_data['fichas_expendidas'] = value

def agregar_fichas(cantidad):
    with shared_data_lock:
        shared_data['fichas_restantes'] += cantidad
    return shared_data['fichas_restantes']

def decrementar_fichas_restantes():
    with shared_data_lock:
        if shared_data['fichas_restantes'] > 0:
            shared_data['fichas_restantes'] -= 1
            shared_data['fichas_expendidas'] += 1
            return True
    return False

def get_motor_activo():
    with shared_data_lock:
        return shared_data['motor_activo']

def set_motor_activo(value):
    with shared_data_lock:
        shared_data['motor_activo'] = value

def get_cuenta():
    with shared_data_lock:
        return shared_data['cuenta']

def set_cuenta(value):
    with shared_data_lock:
        shared_data['cuenta'] = value

def add_to_cuenta(value):
    with shared_data_lock:
        shared_data['cuenta'] += value

def get_r_cuenta():
    with shared_data_lock:
        return shared_data['r_cuenta']

def set_r_cuenta(value):
    with shared_data_lock:
        shared_data['r_cuenta'] = value

def add_to_r_cuenta(value):
    with shared_data_lock:
        shared_data['r_cuenta'] += value

def get_r_sal():
    with shared_data_lock:
        return shared_data['r_sal']

def set_r_sal(value):
    with shared_data_lock:
        shared_data['r_sal'] = value

def add_to_r_sal(value):
    with shared_data_lock:
        shared_data['r_sal'] += value

def get_promo_count(promo_num):
    with shared_data_lock:
        return shared_data[f'promo{promo_num}_count']

def increment_promo_count(promo_num):
    with shared_data_lock:
        shared_data[f'promo{promo_num}_count'] += 1

def set_promo_count(promo_num, value):
    with shared_data_lock:
        shared_data[f'promo{promo_num}_count'] = value

# Función para procesar comandos desde la cola (llamada por el core)
def process_gui_commands():
    while not gui_to_core_queue.empty():
        command = gui_to_core_queue.get()
        # Procesar comando
        if command['type'] == 'add_fichas':
            agregar_fichas(command['cantidad'])
        elif command['type'] == 'promo':
            promo_num = command['promo_num']
            fichas = command['fichas']
            agregar_fichas(fichas)
            increment_promo_count(promo_num)
        # Otros comandos si es necesario
