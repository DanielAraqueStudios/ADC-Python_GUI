#include <stdio.h>
#include "stm32f7xx.h"
#include <string.h>
#include <stdlib.h>
#include <cmath>

// Flags y variables de control
uint8_t flag = 0, i, cont = 0;
unsigned char d;
char text[64]; // Buffer para mensajes
char cmd_buffer[32]; // Buffer para comandos recibidos
uint8_t cmd_index = 0;

// Variables ADC2 - distancia sharp
volatile uint16_t data_value_adc2;
volatile float voltaje1;
volatile double distancesharp;

// Variables ADC2 - intensidad lumínica
volatile uint16_t data_value_adc1;
volatile float voltaje2;
volatile double pesog;

// Variables para control de tiempos
uint32_t tiempo1 = 1; // Tiempo de muestreo para ADC2 (distancia sharp)
uint32_t tiempo2 = 1; // Tiempo de muestreo para ADC1 (intensidad lumínica)
char time_unit = 's'; // 'm' para ms, 's' para segundos, 'M' para minutos

// Variables para filtro promedio
#define MAX_SAMPLES 50
float temp_buffer[MAX_SAMPLES];
float peso_buffer[MAX_SAMPLES];
uint8_t temp_index = 0;
uint8_t peso_index = 0;
uint8_t temp_samples = 10; // Número de muestras por defecto para distancia sharp
uint8_t peso_samples = 10; // Número de muestras por defecto para intensidad lumínica
uint8_t filtro_temp = 0;   // 0: Sin filtro, 1: Con filtro
uint8_t filtro_peso = 0;   // 0: Sin filtro, 1: Con filtro

// Función para calcular promedio
float calcularPromedio(float buffer[], uint8_t num_samples) {
    float sum = 0.0f;
    for (uint8_t i = 0; i < num_samples; i++) {
        sum += buffer[i];
    }
    return sum / num_samples;
}

void SysTick_Wait(uint32_t n) {
    SysTick->LOAD = n - 1;
    SysTick->VAL = 0; 
    while (((SysTick->CTRL & 0x00010000) >> 16) == 0); 
}

void SysTick_ms(uint32_t x) {
    for (uint32_t i = 0; i < x; i++) {
        SysTick_Wait(16000); // Para un reloj de 16 MHz, esto da 1 ms
    }
}

// Función para enviar cadena por UART
void UART_Send_String(const char* str) {
    for (uint32_t i = 0; i < strlen(str); i++) {
        USART3->TDR = str[i];
        while (((USART3->ISR & 0x80) >> 7) == 0) {} // Esperar a que se complete la transmisión
    }
}

// Función para procesar los comandos recibidos por UART
void procesar_comando(const char* cmd) {
    char temp[32];
    strcpy(temp, cmd);
    
    char* tipo = strtok(temp, ":");
    char* valor = strtok(NULL, "\r\n");
    
    if (tipo == NULL) return;
    
    // Manejo especial para el comando STATUS que no requiere valor
    if (strcmp(tipo, "STATUS") == 0) {
        sprintf(text, "INFO:STATUS:T1=%lu,T2=%lu,TU=%c,FT=%d,FP=%d,ST=%d,SP=%d,RUN=%d\r\n", 
                tiempo1, tiempo2, time_unit, filtro_temp, filtro_peso, temp_samples, peso_samples, flag);
        UART_Send_String(text);
        return;
    }
    
    // Manejo especial para los comandos a y b que no requieren valor
    if (strcmp(tipo, "a") == 0) {
        flag = 1; // Activar adquisición
        sprintf(text, "OK:a\r\n");
        UART_Send_String(text);
        return;
    }
    
    if (strcmp(tipo, "b") == 0) {
        flag = 0; // Detener adquisición
        sprintf(text, "OK:b\r\n");
        UART_Send_String(text);
        return;
    }
    
    // Para el resto de comandos, validar que tengan valor
    if (valor == NULL) {
        sprintf(text, "ERROR:Valor requerido para %s\r\n", tipo);
        UART_Send_String(text);
        return;
    }
    
    // Procesar comandos con valores
    if (strcmp(tipo, "T1") == 0) {
        // Cambiar tiempo de muestreo para distancia sharp
        int val = atoi(valor);
        if (val > 0) {
            tiempo1 = val;
            sprintf(text, "OK:T1:%d\r\n", val);
            UART_Send_String(text);
            
            // Debug - confirmar el comando recibido
            sprintf(text, "DEBUG:Tiempo distancia sharp actualizado a %lu %c\r\n", tiempo1, time_unit);
            UART_Send_String(text);
        }
    } else if (strcmp(tipo, "T2") == 0) {
        // Cambiar tiempo de muestreo para intensidad lumínica
        int val = atoi(valor);
        if (val > 0) {
            tiempo2 = val;
            sprintf(text, "OK:T2:%d\r\n", val);
            UART_Send_String(text);
            
            // Debug - confirmar el comando recibido
            sprintf(text, "DEBUG:Tiempo intensidad lumínica actualizado a %lu %c\r\n", tiempo2, time_unit);
            UART_Send_String(text);
        }
    } else if (strcmp(tipo, "TU") == 0) {
        // Cambiar unidad de tiempo (m, s, M)
        if (valor[0] == 'm' || valor[0] == 's' || valor[0] == 'M') {
            time_unit = valor[0];
            sprintf(text, "OK:TU:%c\r\n", time_unit);
            UART_Send_String(text);
            
            // Debug - confirmar el comando recibido
            sprintf(text, "DEBUG:Unidad de tiempo actualizada a %c\r\n", time_unit);
            UART_Send_String(text);
        }
    } else if (strcmp(tipo, "FT") == 0) {
        // Filtro distancia sharp (0=off, 1=on)
        filtro_temp = (atoi(valor) == 0) ? 0 : 1;
        sprintf(text, "OK:FT:%d\r\n", filtro_temp);
        UART_Send_String(text);
    } else if (strcmp(tipo, "FP") == 0) {
        // Filtro intensidad lumínica (0=off, 1=on)
        filtro_peso = (atoi(valor) == 0) ? 0 : 1;
        sprintf(text, "OK:FP:%d\r\n", filtro_peso);
        UART_Send_String(text);
    } else if (strcmp(tipo, "ST") == 0) {
        // Muestras para filtro distancia sharp
        int val = atoi(valor);
        if (val > 0 && val <= MAX_SAMPLES) {
            temp_samples = val;
            sprintf(text, "OK:ST:%d\r\n", temp_samples);
            UART_Send_String(text);
        }
    } else if (strcmp(tipo, "SP") == 0) {
        // Muestras para filtro intensidad lumínica
        int val = atoi(valor);
        if (val > 0 && val <= MAX_SAMPLES) {
            peso_samples = val;
            sprintf(text, "OK:SP:%d\r\n", peso_samples);
            UART_Send_String(text);
        }
    } else {
        // Comando desconocido
        sprintf(text, "ERROR:Comando desconocido: %s\r\n", tipo);
        UART_Send_String(text);
    }
}

extern "C" {
    // Interrupción del botón de usuario
    void EXTI15_10_IRQHandler(void) {
        EXTI->PR |= (1<<13); // Limpiar flag de interrupción para EXTI13
        if (((GPIOC->IDR & (1<<13)) >> 13) == 1) {
            // Cambiar estado de adquisición
            flag = !flag;
            
            // Notificar cambio
            if (flag) {
                sprintf(text, "INFO:Button pressed - acquisition started\r\n");
            } else {
                sprintf(text, "INFO:Button pressed - acquisition stopped\r\n");
            }
            UART_Send_String(text);
        }
    }

    // Interrupción del Timer 2 - Muestreo dedistancia sharp
    void TIM2_IRQHandler(void) { 
        TIM2->SR &= ~(1<<0); // Limpiar el flag de interrupción del TIM2
        
        // Solo enviar datos si la adquisición está activa
        if (flag) {
            // Tomar lectura del ADC2 distancia sharp
            ADC2->CR2 |= (1<<30); // Iniciar conversión A/D
            while (((ADC2->SR & (1<<1)) >> 1) == 0) {} // Esperar a que termine la conversión
            ADC2->SR &= ~(1<<1); // Limpiar el flag EOC
            data_value_adc2 = ADC2->DR;
            voltaje2 = (float)data_value_adc2 * (3.3f / 4095.0f); // Corrección para resolución completa de 12 bits
            distancesharp=25.63f*pow(voltaje2, -1.268f); // Conversión a distancia en cm
            
            // Aplicar filtro promedio si está activado
            if (filtro_temp) {
                temp_buffer[temp_index] = distancesharp;
                temp_index = (temp_index + 1) % temp_samples;
                distancesharp = calcularPromedio(temp_buffer, temp_samples);
            }
            
            // Enviar datos formateados por UART
            sprintf(text, "TEMP:%.2f\r\n", distancesharp);
            UART_Send_String(text);
            
            // Toggle LED para indicar actividad
            GPIOB->ODR ^= (1<<7);
        }
    }

    // Interrupción del Timer 5 - Muestreo de intensidad lumínica
    void TIM5_IRQHandler(void) { 
        TIM5->SR &= ~(1<<0); // Limpiar el flag de interrupción del TIM5
        
        // Solo enviar datos si la adquisición está activa
        if (flag) {
            // Tomar lectura del ADC1 (intensidad lumínica)
            ADC1->CR2 |= (1<<30); // Iniciar conversión A/D
            while (((ADC1->SR & (1<<1)) >> 1) == 0) {} // Esperar a que termine la conversión
            ADC1->SR &= ~(1<<1); // Limpiar el flag EOC
            data_value_adc1 = ADC1->DR;
            voltaje1 = data_value_adc1 * (3.3 / 990); // Corrección para resolución completa de 10 bits
            pesog = (voltaje1 * 303.03f);
            
            // Aplicar filtro promedio si está activado
            if (filtro_peso) {
                peso_buffer[peso_index] = pesog;
                peso_index = (peso_index + 1) % peso_samples;
                pesog = calcularPromedio(peso_buffer, peso_samples);
            }
            
            // Enviar datos formateados por UART
            sprintf(text, "intensidad lumínica:%.2f\r\n", pesog);
            UART_Send_String(text);
        }
    }
    
    // Interrupción del USART3 - Recepción de comandos
    void USART3_IRQHandler(void) { 
        if (((USART3->ISR & 0x20) >> 5) == 1) { // Comprobar RXNE flag
            d = USART3->RDR;
            
            if (d == 'a') {
                flag = 1; // Comando para iniciar
                // Enviar confirmación explícita
                UART_Send_String("OK:a\r\n");
                // Debug - confirmar activación
                UART_Send_String("DEBUG:Adquisicion activada\r\n");
            } else if (d == 'b') {
                flag = 0; // Comando para detener
                // Enviar confirmación explícita
                UART_Send_String("OK:b\r\n");
                // Debug - confirmar desactivación
                UART_Send_String("DEBUG:Adquisicion detenida\r\n");
            } else if (d == '\n' || d == '\r') {
                // Fin de comando, procesarlo
                if (cmd_index > 0) {
                    cmd_buffer[cmd_index] = '\0';
                    procesar_comando(cmd_buffer);
                    cmd_index = 0;
                }
            } else {
                // Agregar carácter al buffer de comandos
                if (cmd_index < sizeof(cmd_buffer) - 1) {
                    cmd_buffer[cmd_index++] = d;
                }
            }
        }
    }
}

int main() {
    // Inicializar buffers para filtros
    for (int i = 0; i < MAX_SAMPLES; i++) {
        temp_buffer[i] = 0.0f;
        peso_buffer[i] = 0.0f;
    }
    
    // ----- Configuración de GPIOs -----
    RCC->AHB1ENR |= ((1<<1) | (1<<2)); // Habilitar reloj para GPIOB y GPIOC
    
    // Configurar GPIOB pins 0 y 7 como salidas (LEDs)
    GPIOB->MODER &= ~((0b11<<0) | (0b11<<14));
    GPIOB->MODER |= ((1<<0) | (1<<14)); 
    GPIOB->OTYPER &= ~((1<<0) | (1<<7)); // Push-pull
    GPIOB->OSPEEDR |= (((1<<1) | (1<<0) | (1<<15) | (1<<14))); // Alta velocidad
    GPIOB->PUPDR &= ~((0b11<<0) | (0b11<<14)); // Sin pull-up/down
    
    // Configurar GPIOC pin 13 como entrada (botón)
    GPIOC->MODER &= ~(0b11<<26);
    GPIOC->OSPEEDR |= ((1<<27) | (1<<26)); // Alta velocidad
    GPIOC->PUPDR &= ~(0b11<<26);
    GPIOC->PUPDR |= (1<<27); // Pull-up
    
    // ----- Configuración de SysTick -----
    SysTick->LOAD = 0x00FFFFFF; 
    SysTick->CTRL |= (0b101); // Habilitar SysTick
    
    // ----- Configuración de interrupciones externas -----
    RCC->APB2ENR |= (1<<14); // Habilitar reloj SYSCFG
    SYSCFG->EXTICR[3] &= ~(0b1111<<4); // Limpiar 
    SYSCFG->EXTICR[3] |= (2<<4); // PC13 para EXTI13 (valor correcto es 2)
    EXTI->IMR |= (1<<13); // Desenmascarar EXTI13
    EXTI->RTSR |= (1<<13); // Trigger en flanco ascendente
    
    // Habilitar interrupción en NVIC
    NVIC_EnableIRQ(EXTI15_10_IRQn); 
    
    // ----- Configuración de USART3 -----
    RCC->AHB1ENR |= (1<<3); // Habilitar reloj para GPIOD
    
    // Configurar PD8 y PD9 para función alternativa USART3
    GPIOD->MODER &= ~((0b11<<18) | (0b11<<16)); 
    GPIOD->MODER |= ((0b10<<16) | (0b10<<18)); // AF mode
    GPIOD->AFR[1] &= ~((0b1111<<4) | (0b1111<<0));
    GPIOD->AFR[1] |= ((0b0111<<0) | (0b0111<<4)); // AF7 para USART3
    
    RCC->APB1ENR |= (1<<18); // Habilitar reloj USART3
    
    // Configurar USART3
    USART3->BRR = 0x683; // 9600 baud a 16MHz
    USART3->CR1 |= ((1<<5) | (1<<3) | (1<<2) | (1<<0)); // Habilitar RX, TX, RXNEIE y enable
    
    // Habilitar interrupción USART3 en NVIC
    NVIC_EnableIRQ(USART3_IRQn); 
    
    // ----- Configuración de ADC2 para PB1 (distancia) -----
    GPIOB->MODER |= (0b11<<2); // PB1 como entrada analógica
    
    RCC->APB2ENR |= (1<<9); // Habilitar reloj ADC2
    ADC2->CR2 |= ((1<<10) | (1<<0)); // EOCS y ADC Enable
    ADC2->CR1 &= ~(0b11<<24); // Resolución a 12 bits
    ADC2->SMPR1 |= (0b111<<6); // Tiempo de muestreo máximo
    ADC2->SQR3 = 9; // Canal 9 para PB1
    
    // ----- Configuración de ADC1 para PC4 intensidad lumínica) -----
    GPIOC->MODER |= (0b11<<8); // PC4 como entrada analógica
    
    RCC->APB2ENR |= (1<<8); // Habilitar reloj ADC1
    ADC1->CR2 |= ((1<<10) | (1<<0)); // EOCS y ADC Enable
    ADC1->CR1 &= ~(0b11<<24); // limpiar bits de resolución
    ADC1->CR1 |= (1<<24); // Resolución a 10 bits
    ADC1->SMPR1 |= (0b111<<12); // Tiempo de muestreo máximo
    ADC1->SQR3 = 14; // Canal 14 para PC4
    
    // ----- Configuración de Timer 2 para muestreo de distancia -----
    RCC->APB1ENR |= (1<<0); // Habilitar reloj TIM2
    TIM2->PSC = 16000 - 1; // Prescaler para 1ms a 16MHz
    TIM2->ARR = 1000; // Periodo inicial (1s)
    TIM2->DIER |= (1<<0); // Habilitar interrupción de update
    TIM2->CR1 |= (1<<0); // Habilitar contador
    
    // Habilitar interrupción TIM2 en NVIC
    NVIC_EnableIRQ(TIM2_IRQn); 
    
    // ----- Configuración de Timer 5 para muestreo de intensidad lumínica -----
    RCC->APB1ENR |= (1<<3); // Habilitar reloj TIM5
    TIM5->PSC = 16000 - 1; // Prescaler para 1ms a 16MHz
    TIM5->ARR = 1000; // Periodo inicial (1s)
    TIM5->DIER |= (1<<0); // Habilitar interrupción de update
    TIM5->CR1 |= (1<<0); // Habilitar contador
    
    // Habilitar interrupción TIM5 en NVIC
    NVIC_EnableIRQ(TIM5_IRQn); 
    
    // Mensaje de inicio
    UART_Send_String("Sistema iniciado v3.0\r\n");
    UART_Send_String("Enviar 'a' para iniciar, 'b' para detener\r\n");
    UART_Send_String("Comandos: T1:tiempo, T2:tiempo, TU:[m,s,M], FT:[0,1], FP:[0,1], ST:muestras, SP:muestras\r\n");
    
    // Bucle principal
    while(1) {
        // Actualizar periodos de muestreo de timers
        uint32_t factor = 1;
        
        switch (time_unit) {
            case 'm': // milisegundos
                factor = 1;
                break;
            case 's': // segundos
                factor = 1000;
                break;
            case 'M': // minutos
                factor = 60000;
                break;
        }
        
        uint32_t arr_value1 = tiempo1 * factor;
        if (arr_value1 < 1) arr_value1 = 1;
        
        uint32_t arr_value2 = tiempo2 * factor;
        if (arr_value2 < 1) arr_value2 = 1;
        
        // Actualizar periodos de los timers solo si han cambiado
        if (TIM2->ARR != arr_value1) {
            TIM2->CR1 &= ~(1<<0); // Deshabilitar timer
            TIM2->ARR = arr_value1;
            TIM2->CNT = 0; // Reiniciar contador
            TIM2->CR1 |= (1<<0); // Habilitar timer
            
            // Informar del cambio
            sprintf(text, "INFO:Timer temp actualizado: %lu ms\r\n", arr_value1);
            UART_Send_String(text);
        }
        
        if (TIM5->ARR != arr_value2) {
            TIM5->CR1 &= ~(1<<0); // Deshabilitar timer
            TIM5->ARR = arr_value2;
            TIM5->CNT = 0; // Reiniciar contador
            TIM5->CR1 |= (1<<0); // Habilitar timer
            
            // Informar del cambio
            sprintf(text, "INFO:Timer intensidad lumínica actualizado: %lu ms\r\n", arr_value2);
            UART_Send_String(text);
        }
        
        if (flag == 1) {
            // Modo de adquisición activo
            GPIOB->ODR ^= (1<<0); // Toggle LED para indicar funcionamiento
            SysTick_ms(500);
        } else {
            // Modo inactivo
            GPIOB->ODR &= ~(1<<0); // LED apagado en modo inactivo
            SysTick_ms(200);
        }
    }
}