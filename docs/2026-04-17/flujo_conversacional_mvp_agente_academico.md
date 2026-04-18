# Flujo conversacional del MVP del agente academico

## Proposito exacto del MVP

El agente academico Lara apoya a estudiantes de Ingenieria de Sistemas en la gestion del tiempo academico, la planificacion de actividades, el seguimiento, la replanificacion y la recomendacion personalizada de metodos de estudio mediante conversacion por WhatsApp e integracion con Microsoft 365, principalmente Outlook Calendar y, en fases posteriores, Microsoft To-Do.

El MVP se enfoca solo en:

1. Gestion de tiempo y agenda.
2. Planificacion de sesiones de estudio basadas en metodo de estudio.
3. Recordatorios y seguimiento.
4. Replanificacion automatica ante cambios.
5. Recomendacion personalizada de metodos de estudio.

## Nota de implementacion actual

El flujo conversacional actual ya inicia con el mensaje de bienvenida y luego solicita autorizacion de tratamiento de datos personales.

La integracion Microsoft OAuth existe en el proyecto mediante `MicrosoftOAuthClient`, URL de autorizacion, intercambio de `authorization_code` y persistencia de tokens. Sin embargo, el onboarding conversacional actual todavia verifica el correo mediante codigo enviado al correo. No existe todavia un subflujo conversacional que detenga el onboarding despues del correo para exigir autorizacion OAuth antes de pedir semestre y promedio.

Si el requisito funcional es que el agente no continue hasta que el estudiante escriba el correo y acepte permisos Microsoft, ese paso debe insertarse entre la captura del correo y la captura del semestre.

## Dominio 0: bienvenida y autorizacion de datos

### Inicio del flujo

**Entrada del estudiante**

El estudiante puede escribir cualquier primer mensaje. Ejemplos:

- `Hola`
- `Quiero organizar mi horario`
- `Buenas`
- Cualquier texto inicial.

**Accion del agente**

El agente no interpreta ese primer texto como respuesta a una pregunta de onboarding. Primero envia el mensaje de bienvenida.

**Mensaje exacto del agente**

```text
¡Hola! 👋✨
Soy Lara, tu Asistente Académico Inteligente 🤖📚

Estoy aquí para ayudarte a organizar tu tiempo, planificar tus actividades y recomendarte métodos de estudio personalizados según tu perfil y tus hábitos académicos 🧠⏳

Sé que la universidad puede ser retadora: parciales, entregas, proyectos, estrés… 😵‍💫
Pero no estás solo/a 💙

Mi objetivo es acompañarte para que:
✅ Aproveches mejor tu tiempo
✅ Reduzcas la procrastinación
✅ Mejores tu rendimiento académico
✅ Estudies con estrategias basadas en evidencia
✅ Tengas una planificación clara y realista

Juntos vamos a construir un plan que se adapte a ti
```

**Siguiente mensaje del agente**

```text
📄 *Autorización para el tratamiento de datos personales – Lara AI*

Antes de continuar, necesito tu autorización para tratar tus datos personales conforme a la normativa colombiana de protección de datos personales.

✅ Al responder *“Sí”*, autorizas de manera previa, expresa e informada a *Lara AI / Universidad Católica de Colombia* para recolectar, almacenar, usar, organizar, actualizar y, en general, tratar tus datos personales únicamente para las siguientes finalidades:

• Gestionar tu registro y perfil dentro de Lara AI.
• Recolectar y usar información académica, de contacto y de planificación.
• Apoyarte en la gestión del tiempo, organización de actividades y recomendaciones de estudio personalizadas.
• Realizar seguimiento funcional, técnico, estadístico y académico del servicio.
• Enviar información relacionada con el funcionamiento del asistente, recordatorios o mensajes asociados al servicio.
• Cumplir obligaciones legales, contractuales y de seguridad de la información.

🔐 Tus datos serán tratados bajo los principios de legalidad, finalidad, libertad, veracidad, transparencia, acceso restringido, seguridad y confidencialidad, de acuerdo con la normativa aplicable.

📩 Como titular de la información, puedes ejercer tus derechos de conocer, actualizar, rectificar y suprimir tus datos, así como revocar esta autorización, mediante solicitud enviada al correo: *jfjaramillo12@ucatolica.edu.co*.

La revocatoria procederá siempre que no exista un deber legal o contractual que impida eliminar o dejar de tratar la información.

⚠️ La información que suministres debe ser veraz, completa y actualizada.

❓ *¿Aceptas el tratamiento de tus datos personales para continuar en Lara AI?*
Responde únicamente: *Sí* o *No*.
```

**Requisito de respuesta del estudiante**

Debe responder `Si`, `Sí` o `No`.

**Acciones segun respuesta**

- Si responde `Si` o `Sí`, el agente continua al dominio de onboarding.
- Si responde `No`, el agente termina el flujo porque no puede tratar datos personales.
- Si responde algo distinto, vuelve a pedir una respuesta valida.

## Dominio 1: onboarding

El objetivo del onboarding es construir un perfil academico minimo, validado y persistible.

### Paso 1: nombre completo

**Mensaje exacto del agente**

```text
¡Hola! 👋 Me alegra acompanarte en este proceso. Para empezar, ¿como te llamas? Puedes escribirme tu nombre y apellido, por ejemplo: Juan Perez
```

**Requisito de respuesta del estudiante**

Debe enviar nombre y apellido, solo letras y espacios.

**Ejemplo valido**

```text
Andres Gomez
```

**Accion del agente**

Valida que existan al menos dos partes, que no haya numeros ni simbolos, normaliza espacios y capitalizacion.

### Paso 2: codigo estudiantil

**Mensaje exacto del agente**

```text
Ahora necesito tu codigo estudiantil 🆔 Escribelo solo en numeros de 8 digitos, por ejemplo: 67000912
```

**Requisito de respuesta del estudiante**

Debe enviar solo numeros, exactamente 8 digitos, y el codigo debe iniciar por `67`.

**Ejemplo valido**

```text
67000921
```

**Accion del agente**

Si el codigo no corresponde al alcance, pregunta si pertenece al programa soportado.

**Mensaje si el codigo no corresponde al programa objetivo**

```text
Este codigo no corresponde a uno de Ingenieria de Sistemas. ¿Perteneces al programa de Ingenieria de Sistemas y Computacion? Responde si o no.
```

Si responde `No`, termina el flujo por fuera de alcance.

### Paso 3: edad

**Mensaje exacto del agente**

```text
Perfecto, {nombre} 🙌 Ahora cuentame, ¿cuantos anos tienes? Escribelo solo en numero, por ejemplo: 20
```

**Requisito de respuesta del estudiante**

Debe enviar un entero entre 15 y 60.

**Ejemplo valido**

```text
20
```

### Paso 4: correo institucional o de pruebas

**Mensaje exacto del agente**

```text
Ahora necesito tu correo institucional o de pruebas 📧 Por favor escribelo completo. Ejemplo: usuario@outlook.com
```

**Requisito de respuesta del estudiante**

Debe enviar un correo valido, sin espacios, con dominio permitido por configuracion.

**Ejemplo valido**

```text
usuario@outlook.com
```

### Paso 4A: verificacion de correo en la implementacion actual

**Mensaje exacto del agente**

```text
¡Gracias! Ya casi terminamos esta parte ✨ Voy a enviarte un codigo de verificacion a tu correo institucional. Cuando lo recibas, escribemelo aqui para continuar.
Codigo enviado 📩
El codigo vence en {minutos} minutos.
```

**Mensaje exacto para pedir codigo**

```text
¿Me compartes el codigo que te llego al correo? 🔐 Escribelo tal como aparece, por ejemplo: 444444
Si no te llega, escribe: reenviar
```

**Requisito de respuesta del estudiante**

Debe enviar el codigo numerico con la longitud configurada, o escribir `reenviar`.

**Accion del agente**

Verifica el codigo. Si coincide, marca `email_verified = true`. Si no coincide o vence, pide reintentar o reenviar.

### Paso 4B: autorizacion Microsoft OAuth requerida por el MVP objetivo

Este paso debe agregarse si el onboarding debe bloquearse hasta que exista conexion Microsoft.

**Mensaje recomendado del agente**

```text
Para ayudarte con tu calendario y recordatorios, necesito que autorices el acceso a tu cuenta.
Te voy a enviar un enlace seguro para iniciar sesión y aprobar los permisos necesarios. 🔐
```

**Accion del backend**

1. Genera una URL de autorizacion unica con `MicrosoftOAuthClient.build_authorization_request`.
2. Incluye `student_id`, `state` seguro, `redirect_uri` y scopes.
3. Envia el enlace por WhatsApp.
4. El estudiante abre el enlace, inicia sesion en Microsoft y acepta permisos.
5. Microsoft redirige al backend con `authorization_code`.
6. El backend llama `exchange_authorization_code`.
7. El sistema persiste la conexion Microsoft.

**Mensaje recomendado despues de conectar**

```text
Listo ✅ Tu calendario quedó conectado correctamente.
```

**Regla funcional**

El agente no debe continuar a semestre hasta que el correo exista y la conexion Microsoft haya quedado autorizada.

### Paso 5: semestre

**Mensaje exacto del agente**

```text
¿En que semestre estas actualmente? 📚 Escribelo solo en numero, por ejemplo: 4
```

**Requisito de respuesta del estudiante**

Debe enviar un entero entre 1 y 15.

### Paso 6: promedio acumulado

**Mensaje exacto del agente**

```text
Por ultimo, ¿cual es tu promedio academico acumulado? ⭐ Escribelo en numero entre 0 y 100, por ejemplo: 76 o 76.5
```

**Requisito de respuesta del estudiante**

Debe enviar un numero entre 0 y 100. Puede tener punto decimal y maximo 2 decimales.

### Paso 7: confirmacion de datos

**Mensaje exacto del agente**

```text
Verifica tu informacion:
Nombre: Andres Gomez
Codigo estudiantil: 67000921
Edad: 32
Correo institucional: usuario90@outlook.com
Correo verificado: Si
Programa: Ingenieria de Sistemas y Computacion
Semestre: 8
Promedio acumulado: 80.0

¿Es correcta? Responde si o no.
```

**Requisito de respuesta del estudiante**

Debe responder `Si` o `No`.

**Acciones segun respuesta**

- Si responde `Si`, el agente persiste el perfil y avanza a horario fijo.
- Si responde `No`, el agente pide el dato a corregir.

**Mensaje exacto para correccion**

```text
¿Que dato deseas corregir? Opciones: nombre, codigo, edad, correo, programa, semestre, promedio.
```

## Dominio 2: horario fijo

El objetivo es conocer la rutina recurrente del estudiante antes de organizar su agenda.

### Paso 1: seleccion de rutina

**Mensaje exacto del agente**

```text
Antes de organizar tu agenda, necesito saber cómo está distribuida tu rutina.
(Escribe el número de la opción que quieres elegir)
Elige una opción:
1. Solo estudio
2. Estudio y trabajo
3. Ninguna de las anteriores
```

**Requisito de respuesta del estudiante**

Debe responder `1`, `2` o `3`. Tambien se aceptan textos equivalentes como `solo estudio`, `estudio y trabajo` o `ninguna`.

### Opcion 1: solo estudio

**Accion del agente**

Guarda `occupation = solo_estudio` y solicita horario academico.

**Mensaje exacto del agente**

```text
📚 Ahora compárteme tu horario académico.

Puedes copiarlo y pegarlo tal como aparece en tu correo o en el sistema donde inscribiste tus materias.

Antes de enviarlo, ten en cuenta estas recomendaciones:

• Indica el día y la hora de inicio y fin de cada materia.
• Escribe cada materia por separado o asegúrate de que estén bien diferenciadas.
• Si usas formato normal, escribe am o pm.
• Si no escribes am/pm, asumiré que usas horario militar.
• Puedes escribir varias materias en un mismo mensaje, una debajo de otra.
• Si una materia se repite en varios días, puedes escribir los días juntos.

Ejemplos válidos:

Lunes - Cálculo - 07:00 a 09:00
Martes y jueves - Física - 10:00 a 12:00
Viernes - Programación - 2:00 pm a 4:00 pm
```

**Requisito de respuesta del estudiante**

Debe enviar materias con:

- Dia o dias.
- Nombre de la materia.
- Hora de inicio.
- Hora de fin.

**Ejemplo valido**

```text
Lunes - Calculo diferencial - 07:00 a 09:00
Martes y jueves - Programacion - 10:00 a 12:00
Viernes - Bases de datos - 2:00 pm a 4:00 pm
```

**Accion del agente**

Interpreta el texto, normaliza dias y horas, crea bloques semanales tipo `academic` y pregunta si desea agregar mas materias.

**Mensaje exacto del agente**

```text
📚 ¿Quieres agregar más materias o ya terminamos con esta parte?
(Escribe el número de la opción que quieres elegir)
1. Sí, quiero agregar más materias
2. No, seguimos
```

**Si el estudiante elige 1**

El agente vuelve a capturar materias adicionales. Tambien puede aceptar que el estudiante envie la opcion y el contenido en el mismo mensaje.

**Si el estudiante elige 2**

El agente inicia confirmacion por seccion.

**Mensaje de confirmacion por seccion**

```text
✅ Este es tu horario académico actual:
(Escribe el número de la opción que quieres elegir)
{lista de materias interpretadas}

¿Está bien así?
1. Sí, está correcto
2. No, quiero cambiar algo
```

### Opcion 2: estudio y trabajo

**Accion del agente**

Guarda `occupation = ambos`, solicita primero horario academico y luego horario laboral.

El horario academico usa el mismo mensaje y reglas de la opcion 1.

Cuando el horario academico queda confirmado, solicita horario laboral.

**Mensaje exacto del agente**

```text
💼 Ahora compárteme tu horario laboral.

Antes de enviarlo, ten en cuenta estas recomendaciones:

• Indica el día o los días en los que trabajas.
• Incluye la hora de inicio y fin.
• Si usas formato normal, escribe am o pm.
• Si no escribes am/pm, asumiré que usas horario militar.
• Si trabajas varios días con el mismo horario, puedes escribirlos juntos.

Ejemplos válidos:

Lunes a viernes - Trabajo - 07:00 a 18:00
Sábado - Trabajo - 8:00 am a 12:00 pm
```

**Requisito de respuesta del estudiante**

Debe enviar dias de trabajo y rango horario.

**Ejemplo valido**

```text
Lunes a viernes - Trabajo - 07:00 a 18:00
Sábado - Trabajo - 8:00 am a 12:00 pm
```

**Mensaje exacto despues de interpretar horario laboral**

```text
💼 ¿Quieres agregar más horarios de trabajo o continuamos?
(Escribe el número de la opción que quieres elegir)
1. Sí, quiero agregar más horarios
2. No, seguimos
```

**Confirmacion por seccion laboral**

```text
✅ Este es tu horario laboral actual:
(Escribe el número de la opción que quieres elegir)
{lista de bloques laborales interpretados}

¿Está bien así?
1. Sí, está correcto
2. No, quiero cambiar algo
```

### Opcion 3: ninguna de las anteriores

**Accion del agente**

Finaliza el flujo porque el MVP necesita que el usuario este estudiando.

**Mensaje exacto del agente**

```text
Soy un agente especializado en gestión del tiempo, planificación de actividades y recomendación de métodos de estudio. Lo siento, no puedo ayudarte en este momento porque necesito que actualmente estés estudiando.
```

### Correccion guiada de horario fijo

Si el estudiante responde que una seccion no esta correcta:

**Mensaje del agente**

```text
✏️ Este es tu horario académico actual:
(Escribe el número del registro que quieres editar)
{lista de registros}

Elige el número de la materia que quieres editar.
```

Despues de escoger el registro:

```text
📚 Vas a editar este materia:
{registro seleccionado}

🛠️ ¿Qué quieres cambiar?
(Escribe el número del cambio que quieres hacer)
1. Nombre
2. Día
3. Horario
4. Eliminar materia
5. Cancelar edición
```

Si cambia el nombre:

```text
✏️ Escribe el nuevo nombre de la materia.
Actual: {registro actual}
```

Si cambia el dia:

```text
📅 Elige el nuevo día:
1. Lunes
2. Martes
3. Miércoles
4. Jueves
5. Viernes
6. Sábado
7. Domingo

Actual: {registro actual}
```

Si cambia horario:

```text
⏰ Escribe el nuevo horario completo.
Envíame la hora de inicio y la hora de fin en un solo mensaje.
Ejemplos válidos: 8:00 am a 10:00 am, 2:30 pm a 4:00 pm o 14:30 a 16:00.
Actual: {registro actual}
```

Despues de actualizar:

```text
✅ Así quedó actualizado:
{registro actualizado}

(Escribe el número de la opción que quieres elegir)
¿Ahora sí quedó bien?
1. Sí, seguimos
2. No, quiero cambiar algo más
```

## Dominio 3: actividades extracurriculares

El objetivo es registrar actividades fijas no academicas que tambien ocupan tiempo semanal.

**Mensaje exacto del agente**

```text
🏃‍♂️ ¿Tienes actividades extracurriculares durante la semana?
Por ejemplo: deporte, gimnasio, cursos, semilleros, reuniones o cualquier otra actividad fija.
(Escribe el número de la opción que quieres elegir)
1. Sí, tengo actividades extracurriculares
2. No, continuemos
```

### Si el estudiante elige 1

**Mensaje exacto del agente**

```text
🏃 Ahora vamos a registrar tus actividades extracurriculares.

Escríbelas en un solo mensaje.

Antes de enviarlo, ten en cuenta estas recomendaciones:

• Indica siempre el día y la hora de inicio y fin.
• Si usas formato normal, escribe am o pm.
• Si no escribes am/pm, asumiré que usas horario militar (por ejemplo: 14:00).
• Puedes escribir varias actividades en el mismo mensaje, una debajo de otra o bien separadas.
• Si una actividad ocurre varios días, puedes escribirlos juntos.

Ejemplos válidos:

Martes y jueves - Gimnasio - 19:00 a 20:30
Sábado - Natación - 8:00 am a 10:00 am
```

**Requisito de respuesta del estudiante**

Debe enviar nombre de actividad, dia o dias, hora de inicio y hora de fin.

**Ejemplo valido**

```text
Martes y jueves - Gimnasio - 19:00 a 20:30
Sábado - Natación - 8:00 am a 10:00 am
```

**Mensaje exacto despues de interpretar actividades**

```text
🎯 ¿Quieres agregar más actividades extracurriculares o continuamos?
(Escribe el número de la opción que quieres elegir)
1. Sí, quiero agregar más actividades
2. No, seguimos
```

### Si el estudiante elige 2

**Mensaje exacto del agente**

```text
Perfecto. Voy a revisar el horario con lo que ya me compartiste.
```

## Dominio 4: vista previa, conflictos, fecha limite y guardado

El objetivo es mostrar la interpretacion completa del horario semanal, detectar cruces, permitir correcciones y guardar el horario fijo.

### Vista previa sin conflictos

**Mensaje del agente**

```text
Aquí tienes la interpretación de tu horario semanal.
🗓️ Esto fue lo que entendí de tu horario semanal:
- Lunes: Cálculo — 07:00-09:00
- Martes: Física — 10:00-12:00

✅ ¿Entendí bien tu horario?
(Escribe el número de la opción que quieres elegir)
1. Sí, está correcto
2. No, quiero corregir algo
```

**Requisito de respuesta del estudiante**

Debe responder `1` si esta correcto o `2` si quiere corregir.

### Vista previa con conflictos

**Mensaje del agente**

```text
⚠️ Encontré cruces en tu horario:
- {Día}: {bloque 1} ({tipo 1}) {hora cruce} se cruza con {bloque 2} ({tipo 2}).

No es lo más recomendable para una buena planificación.
(Escribe el número de la opción que quieres elegir)
1. Sí, dejarlo así
2. No, quiero corregirlo
```

**Acciones segun respuesta**

- Si responde `1`, el agente acepta el cruce conscientemente.
- Si responde `2`, abre menu de correccion.

**Mensaje si acepta cruces**

```text
Entendido. Dejaré esos cruces como aceptados conscientemente.
✅ ¿El horario completo quedó correcto?
(Escribe el número de la opción que quieres elegir)
1. Sí, está correcto
2. No, quiero corregir algo
```

### Menu de correccion final

**Mensaje del agente**

```text
✏️ ¿Qué parte quieres corregir?
1. Horario académico
2. Horario laboral
3. Actividades extracurriculares
```

Si el estudiante solo estudia, el menu no incluye horario laboral.

### Fecha limite del horario fijo

Cuando el estudiante confirma que el horario esta correcto:

**Mensaje exacto del agente**

```text
📅 Antes de guardarlo en Outlook, necesito la fecha límite de este horario fijo.
Escríbela en uno de estos formatos:
1. YYYY-MM-DD
2. DD/MM/YYYY
Ejemplo: 2026-06-30
```

**Requisito de respuesta del estudiante**

Debe enviar fecha valida en formato `YYYY-MM-DD` o `DD/MM/YYYY`.

**Ejemplo valido**

```text
2026-06-30
```

**Mensaje del agente**

```text
📅 Perfecto. Voy a guardar tu horario semanal hasta el {fecha}.
```

### Persistencia local

**Mensaje exacto si guarda correctamente**

```text
✅ Tu horario semanal quedó guardado correctamente.
```

### Sincronizacion con Outlook

**Mensaje si Outlook sincroniza correctamente**

```text
✅ También guardé tu horario fijo en Outlook hasta el {fecha}.
```

**Mensaje si no existe conexion Microsoft**

```text
Tu horario quedó guardado en el sistema, pero no pude sincronizarlo con Outlook.
Detalle técnico: No existe una conexión Microsoft persistida para este estudiante. Completa OAuth antes de sincronizar Outlook.
```

## Dominio 5: Radar de estudio y recomendacion personalizada

El objetivo es identificar debilidades academicas y recomendar tecnicas de estudio personalizadas.

### Introduccion del Radar

**Mensaje exacto del agente**

```text
Vamos a activar tu Radar de estudio 🧭
Te haré 10 mini retos para detectar qué obstáculos aparecen cuando estudias y qué técnicas pueden ayudarte más.
No hay respuestas buenas o malas: la idea es entender cómo estudias hoy para construir un método más personalizado para ti.

Responde pensando en cómo has estudiado en las últimas 2 o 3 semanas.
Usa un número:
0 = Casi nunca
1 = A veces
2 = Me pasa seguido
3 = Me pasa casi siempre
```

**Requisito de respuesta del estudiante**

En cada reto debe responder un numero del 0 al 3.

### Escala de respuesta

```text
0 = Casi nunca
1 = A veces
2 = Me pasa seguido
3 = Me pasa casi siempre
```

### Reto 1

```text
Reto 1/10 · Encender el modo estudio 🚀
Progreso 1/10: 🟩⬜⬜⬜⬜⬜⬜⬜⬜⬜

Cuando sé que tengo cosas pendientes, me cuesta dar el primer paso y empezar a estudiar.

Responde con un número:
0 = Casi nunca
1 = A veces
2 = Me pasa seguido
3 = Me pasa casi siempre
```

### Reto 2

```text
Reto 2/10 · Mantener el foco 🎯
Progreso 2/10: 🟩🟩⬜⬜⬜⬜⬜⬜⬜⬜

Cuando estudio, pierdo la concentración con facilidad por el celular, redes sociales o interrupciones.

Responde con un número:
0 = Casi nunca
1 = A veces
2 = Me pasa seguido
3 = Me pasa casi siempre
```

### Reto 3

```text
Reto 3/10 · Explicar para entender 🗣️
Progreso 3/10: 🟩🟩🟩⬜⬜⬜⬜⬜⬜⬜

Después de estudiar un tema, me cuesta explicarlo con mis propias palabras de forma clara.

Responde con un número:
0 = Casi nunca
1 = A veces
2 = Me pasa seguido
3 = Me pasa casi siempre
```

### Reto 4

```text
Reto 4/10 · Recordar sin mirar 🧠
Progreso 4/10: 🟩🟩🟩🟩⬜⬜⬜⬜⬜⬜

Cuando repaso, dependo mucho de releer o subrayar, pero me cuesta responder sin mirar los apuntes.

Responde con un número:
0 = Casi nunca
1 = A veces
2 = Me pasa seguido
3 = Me pasa casi siempre
```

### Reto 5

```text
Reto 5/10 · Apuntes que sí ayuden 📝
Progreso 5/10: 🟩🟩🟩🟩🟩⬜⬜⬜⬜⬜

Mis apuntes no me ayudan mucho a repasar después, porque me cuesta encontrar ideas clave, preguntas importantes o resúmenes claros.

Responde con un número:
0 = Casi nunca
1 = A veces
2 = Me pasa seguido
3 = Me pasa casi siempre
```

### Reto 6

```text
Reto 6/10 · Ver el mapa completo 🗺️
Progreso 6/10: 🟩🟩🟩🟩🟩🟩⬜⬜⬜⬜

Cuando un tema es amplio o teórico, me cuesta organizar las ideas y entender cómo se conectan entre sí.

Responde con un número:
0 = Casi nunca
1 = A veces
2 = Me pasa seguido
3 = Me pasa casi siempre
```

### Reto 7

```text
Reto 7/10 · Recordar detalles clave 🔑
Progreso 7/10: 🟩🟩🟩🟩🟩🟩🟩⬜⬜⬜

Me cuesta recordar con precisión definiciones, listas, clasificaciones, pasos o términos importantes.

Responde con un número:
0 = Casi nunca
1 = A veces
2 = Me pasa seguido
3 = Me pasa casi siempre
```

### Reto 8

```text
Reto 8/10 · No olvidar tan rápido ⏳
Progreso 8/10: 🟩🟩🟩🟩🟩🟩🟩🟩⬜⬜

Si no repaso un tema después de varios días, olvido rápido gran parte de lo que había estudiado.

Responde con un número:
0 = Casi nunca
1 = A veces
2 = Me pasa seguido
3 = Me pasa casi siempre
```

### Reto 9

```text
Reto 9/10 · Equilibrar varias materias ⚖️
Progreso 9/10: 🟩🟩🟩🟩🟩🟩🟩🟩🟩⬜

Cuando tengo varias materias o tipos de ejercicios, suelo dedicar demasiado tiempo a una sola y dejo las demás para después.

Responde con un número:
0 = Casi nunca
1 = A veces
2 = Me pasa seguido
3 = Me pasa casi siempre
```

### Reto 10

```text
Reto 10/10 · Cambiar de chip 🔄
Progreso 10/10: 🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩

Cuando cambio entre materias o entre tipos de problemas, me cuesta identificar qué enfoque o procedimiento usar en cada caso.

Responde con un número:
0 = Casi nunca
1 = A veces
2 = Me pasa seguido
3 = Me pasa casi siempre
```

### Si la respuesta es invalida

**Mensaje exacto del agente**

```text
Necesito que me respondas solo con un número del 0 al 3 para seguir con tu Radar 🧭
0 = Casi nunca
1 = A veces
2 = Me pasa seguido
3 = Me pasa casi siempre
```

### Desempate del Radar

Si el resultado queda con tecnicas muy parejas, el agente hace 3 retos extra.

**Mensaje introductorio**

```text
Tu Radar quedó con señales bastante parejas, así que voy a hacerte 3 retos extra para afinar mejor tu perfil de estudio 🎯
Con esto podré priorizar con más precisión las técnicas que más te pueden ayudar.

Responde con un número del 1 al 4.
```

**Reto extra 1**

```text
Reto extra 1 · ¿Qué te frena más? 🚦
Progreso 1/3: 🟩⬜⬜

Cuando vas a estudiar, ¿qué sientes que más te frena en este momento?

1. Me cuesta empezar.
2. Me cuesta concentrarme y sostener el foco.
3. Me cuesta recordar sin mirar apuntes.
4. Olvido rápido si pasan varios días.

Responde con un número del 1 al 4.
```

**Reto extra 2**

```text
Reto extra 2 · ¿Dónde se enreda más el estudio? 🧩
Progreso 2/3: 🟩🟩⬜

¿En cuál de estas situaciones sientes más dificultad?

1. En temas amplios o teóricos, porque no veo cómo se conectan las ideas.
2. En definiciones, listas, clasificaciones o términos exactos.
3. En apuntes que luego no me sirven bien para repasar.
4. En explicar con mis propias palabras lo que supuestamente entendí.

Responde con un número del 1 al 4.
```

**Reto extra 3**

```text
Reto extra 3 · Cambiar de estrategia 🔄
Progreso 3/3: 🟩🟩🟩

Cuando estudias varias materias o tipos de ejercicios, ¿qué te cuesta más?

1. Me quedo demasiado tiempo en una sola materia.
2. Me cuesta cambiar entre tipos de problemas o enfoques.
3. Prefiero releer antes que probar si realmente recuerdo.
4. Necesito una forma más clara de organizar el estudio por bloques.

Responde con un número del 1 al 4.
```

**Mensaje si una respuesta extra es invalida**

```text
Para afinar bien tu perfil necesito una opción del 1 al 4 🎯
Respóndeme solo con un número para seguir.
```

### Consolidacion del Radar

**Mensaje si no hubo desempate**

```text
Perfecto. Voy a consolidar tu Radar de estudio.
```

**Mensaje si hubo desempate**

```text
Listo. Voy a consolidar el resultado afinado de tu Radar.
```

### Cierre del Radar

**Mensaje base del agente**

```text
Listo, ya identifiqué cómo puedes estudiar de forma más efectiva según tu perfil 📘

Lo que más te conviene fortalecer ahora es esto:

{fortalecimiento 1}
{fortalecimiento 2}
{fortalecimiento 3}

Tu perfil sugiere que aprendes mejor cuando estudias {acciones de aprendizaje}, no solo leyendo.
Por eso, tu método de estudio debería combinar {piezas del metodo}.

Para llevarlo a la práctica:
{guia pedagogica generada con apoyo del RAG}
```

## Estado posterior al Radar

En el estado actual del proyecto, el flujo termina despues del cierre del Radar. La logica posterior esta desactivada para permitir la refactorizacion de la ultima fase.

Actualmente no se ejecutan automaticamente:

- Captura de prioridades semanales.
- Construccion del plan de estudio.
- Materializacion de sesiones de estudio.
- Recordatorios.
- Seguimiento.
- Replanificacion posterior al Radar.

El RAG se mantiene como apoyo de grounding para enriquecer la recomendacion pedagogica, no como respuesta directa ni como sustituto del LLM.

## Mapa de nodos y logica por dominio

### Dominio 0: bienvenida y consentimiento

**Nodos principales**

- `welcome_consent`

**Logica implicada**

- Detecta si es el primer contacto.
- Envia primero bienvenida.
- Luego solicita autorizacion de tratamiento de datos.
- Solo avanza si el estudiante acepta.

**Archivos**

- `src/agents/support/nodes/welcome_consent/node.py`
- `src/agents/support/nodes/welcome_consent/prompt.py`

### Dominio 1: onboarding

**Nodos principales**

- `collect_profile`
- `send_email_verification`
- `verify_email_code`
- `confirm_profile`
- `persist_profile`

**Logica implicada**

- Captura nombre, codigo, edad, correo, semestre y promedio.
- Valida cada campo con reglas deterministas.
- Verifica correo con codigo en la implementacion actual.
- Confirma datos antes de persistir.
- Persiste perfil y avanza al flujo de horarios.

**Archivos**

- `src/agents/support/flows/onboarding/collect_profile.py`
- `src/agents/support/onboarding/messages.py`
- `src/agents/support/onboarding/validators.py`
- `src/agents/support/nodes/send_email_verification/node.py`
- `src/agents/support/nodes/verify_email_code/node.py`
- `src/agents/support/nodes/confirm_profile/node.py`
- `src/agents/support/nodes/persist_profile/node.py`

**OAuth recomendado**

- `src/integrations/microsoft_graph/auth_client.py`
- `scripts/microsoft_oauth_authorize.py`
- `scripts/microsoft_oauth_exchange_code.py`

### Dominio 2: horario fijo

**Nodos principales**

- `request_schedules`
- `parse_schedules_to_events`

**Servicios de logica**

- `schedule_capture_service`
- `schedule_parsing_service`
- `section_confirmation_service`

**Logica implicada**

- Pregunta si el estudiante solo estudia, estudia y trabaja, o no aplica.
- Captura horario academico.
- Captura horario laboral si aplica.
- Acepta texto y, si hay imagen, intenta extraer horario con LLM.
- Pide aclaraciones si faltan nombre, dia, hora o AM/PM.
- Permite agregar mas registros.
- Confirma cada seccion antes de continuar.

**Archivos**

- `src/agents/support/nodes/request_schedules/node.py`
- `src/agents/support/nodes/request_schedules/prompt.py`
- `src/agents/support/flows/scheduling/schedule_capture_service.py`
- `src/agents/support/flows/scheduling/schedule_parsing_service.py`
- `src/agents/support/flows/scheduling/section_confirmation_service.py`

### Dominio 3: actividades extracurriculares

**Nodos principales**

- `ask_extracurricular`
- `collect_extracurricular_details`

**Logica implicada**

- Pregunta si tiene actividades extracurriculares.
- Captura actividades fijas con dia y horario.
- Pide aclaraciones si faltan datos.
- Permite agregar mas actividades.
- Confirma la seccion extracurricular.

**Archivos**

- `src/agents/support/nodes/ask_extracurricular/node.py`
- `src/agents/support/nodes/ask_extracurricular/prompt.py`
- `src/agents/support/flows/extracurricular/collect_extracurricular_details.py`
- `src/agents/support/nodes/collect_extracurricular_details/prompt.py`

### Dominio 4: vista previa, validacion y sincronizacion

**Nodos principales**

- `build_draft_schedule`
- `render_schedule_preview`
- `validate_schedule`
- `apply_schedule_correction`
- `persist_schedule`
- `sync_fixed_schedule`

**Logica implicada**

- Construye el resumen semanal.
- Detecta cruces.
- Permite aceptar o corregir conflictos.
- Solicita fecha limite del horario fijo.
- Guarda el horario en base de datos.
- Intenta sincronizarlo con Outlook.

**Archivos**

- `src/agents/support/nodes/build_draft_schedule/node.py`
- `src/agents/support/nodes/render_schedule_preview/node.py`
- `src/agents/support/nodes/validate_schedule/node.py`
- `src/agents/support/nodes/apply_schedule_correction/node.py`
- `src/agents/support/nodes/persist_schedule/node.py`
- `src/agents/support/nodes/sync_fixed_schedule/node.py`
- `src/services/sync/outlook_fixed_schedule_sync_service.py`

### Dominio 5: Radar de estudio y recomendacion

**Nodos principales**

- `collect_study_profile`
- `collect_study_profile_tiebreaker`
- `persist_study_profile`

**Logica implicada**

- Ejecuta cuestionario de 10 retos.
- Calcula debilidades academicas y ranking de tecnicas.
- Si hay empate, ejecuta 3 preguntas extra.
- Persiste el resultado del Radar.
- Usa el RAG como apoyo pedagogico para grounding.
- Cierra el flujo actual.

**Archivos**

- `src/agents/support/nodes/collect_study_profile/node.py`
- `src/agents/support/nodes/collect_study_profile_tiebreaker/node.py`
- `src/agents/support/nodes/persist_study_profile/node.py`
- `src/agents/support/personalization/formatter.py`
- `src/services/personalization/questionnaire.py`
- `src/services/personalization/scoring.py`
- `src/services/study_recommendations/service.py`

### Flujo posterior al Radar desactivado

**Nodos existentes pero no activos automaticamente despues del Radar**

- `collect_priorities`
- `build_study_plan`
- `handle_academic_update`

**Logica actual**

- El enrutamiento retorna `end` para las fases `priorities`, `study_plan` y `running`.
- `persist_study_profile` cierra el flujo con `phase = "end"`.
- Las actualizaciones academicas puntuales no reactivan la generacion automatica del plan.

**Archivo principal**

- `src/agents/support/agent.py`
