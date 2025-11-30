#!/bin/bash

# Actualizar el sistema
echo "Actualizando el sistema..."
sudo apt-get update -y
sudo apt-get upgrade -y

# Instalar Node.js y npm si no están instalados
if ! command -v node &> /dev/null
then
    echo "Node.js no está instalado. Instalando Node.js..."
    curl -sL https://deb.nodesource.com/setup_14.x | sudo -E bash -
    sudo apt-get install -y nodejs
fi

if ! command -v npm &> /dev/null
then
    echo "npm no está instalado. Instalando npm..."
    sudo apt-get install -y npm
fi

# Instalar las dependencias del proyecto
echo "Instalando dependencias del proyecto..."
npm install

# Verificar si la instalación fue exitosa
if [ $? -eq 0 ]; then
    echo "Las dependencias se han instalado correctamente."
else
    echo "Hubo un error al instalar las dependencias."
    exit 1
fi