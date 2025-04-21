# Sistema de Adquisición de Datos con STM32F7

Este proyecto implementa un sistema de adquisición de datos utilizando un microcontrolador STM32F7, capaz de medir distancia mediante un sensor Sharp y la intensidad lumínica a través de un sensor de luz.

## Configuración de Hardware

### Pines Utilizados
- **UART/USART3**:
  - PD8: TX (Transmisión)
  - PD9: RX (Recepción)
  - Configuración: 9600 baudios, 8 bits, sin paridad, 1 bit de parada

- **ADC**:
  - PB1 (ADC2 Canal 9): Sensor Sharp de distancia
  - PC4 (ADC1 Canal 14): Sensor de intensidad lumínica

- **LEDs Indicadores**:
  - PB0: LED de estado de adquisición
  - PB7: LED de actividad de muestreo

- **Botón de Control**:
  - PC13: Botón de usuario para iniciar/detener adquisición

## Componentes del Sistema

### 1. UART/USART3
- Permite la comunicación bidireccional con el PC
- Comandos disponibles:
  - `a`: Iniciar adquisición
  - `b`: Detener adquisición
  - `T1:[valor]`: Tiempo de muestreo para distancia
  - `T2:[valor]`: Tiempo de muestreo para luz
  - `TU:[m|s|M]`: Unidad de tiempo (milisegundos, segundos, minutos)
  - `FT:[0|1]`: Activar/desactivar filtro de temperatura
  - `FL:[0|1]`: Activar/desactivar filtro de luz
  - `ST:[valor]`: Número de muestras para filtro de temperatura
  - `SL:[valor]`: Número de muestras para filtro de luz
  - `STATUS`: Consultar estado del sistema

### 2. ADCs (Conversores Analógico-Digital)
- **ADC2 (Sensor Sharp)**:
  - Resolución: 12 bits (0-4095)
  - Fórmula de conversión: distancia = 25.63 × voltaje^(-1.268)
  - Rango de medición: 10-80cm aproximadamente

- **ADC1 (Sensor de Luz)**:
  - Resolución: 10 bits (0-1023)
  - Fórmula de conversión: intensidad = (3.3-voltaje)/0.03
  - Medición en unidades de lux

### 3. Timers
- **Timer 2**: Controla el muestreo del sensor de distancia
  - Base de tiempo: 1ms
  - Período configurable mediante comando T1

- **Timer 5**: Controla el muestreo del sensor de luz
  - Base de tiempo: 1ms
  - Período configurable mediante comando T2

### 4. Sistema de Filtrado
- Implementa un filtro de promedio móvil
- Configurable hasta 50 muestras
- Activable/desactivable independientemente para cada sensor
- Ayuda a reducir el ruido en las mediciones

## Protocolo de Comunicación

### Formato de Mensajes
1. **Comandos de entrada**:
   ```
   [COMANDO]:[VALOR]\r\n
   ```

2. **Mensajes de salida**:
   - Datos: 
     ```
     TEMP:[valor]\r\n
     intensidad lumínica:[valor]\r\n
     ```
   - Confirmaciones:
     ```
     OK:[comando]\r\n
     ```
   - Errores:
     ```
     ERROR:[mensaje]\r\n
     ```
   - Información:
     ```
     INFO:[mensaje]\r\n
     ```

## Funcionamiento

1. Al iniciar, el sistema configura todos los periféricos y muestra un mensaje de bienvenida.

2. La adquisición puede iniciarse/detenerse de dos formas:
   - Mediante el botón PC13
   - Enviando comandos 'a'/'b' por UART

3. Durante la adquisición:
   - El LED PB0 parpadea cada 500ms
   - El LED PB7 parpadea con cada muestra de distancia
   - Los datos se envían por UART según los tiempos configurados

4. Los tiempos de muestreo son configurables en tiempo real sin detener la adquisición

## Notas de Implementación

- El sistema utiliza interrupciones para minimizar la carga del procesador
- Los filtros implementan un buffer circular para optimizar memoria
- Incluye protección contra comandos malformados
- Los timers se actualizan dinámicamente sin perder sincronización
- Sistema de debug integrado para facilitar la depuración

## Dependencias Hardware

- STM32F7 series microcontroller
- Sensor Sharp (conectado a PB1)
- Sensor de luz (conectado a PC4)
- 2 LEDs (conectados a PB0 y PB7)
- Botón (conectado a PC13)
- Interfaz UART-USB para comunicación con PC

## Instrucciones de Uso

1. Conectar el hardware según las especificaciones de pines
2. Establecer conexión serial a 9600 baudios
3. El sistema inicia en modo detenido
4. Usar comandos o botón para control
5. Monitorear respuestas por UART para verificar operación
