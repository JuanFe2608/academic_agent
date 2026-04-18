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

## La logica anterior es todo lo que se lleva del agente: 

### Alcnace del proyecto: 

1) Sí atiende

El agente sí atiende solicitudes relacionadas con la organización y apoyo académico del estudiante dentro del alcance del MVP:

A. Perfil y datos del estudiante
Registrar datos básicos y académicos del estudiante.
Validar y persistir esos datos.
Recuperar información relevante del estudiante para personalizar respuestas sin pedir lo mismo varias veces.
Usar memoria resumida/estructurada para ahorrar tokens y mantener contexto operativo.
B. Horarios y actividades
Registrar, visualizar, modificar y eliminar horarios fijos por lenguaje natural.
Registrar, visualizar, modificar y eliminar actividades académicas por lenguaje natural.
Detectar datos faltantes en horarios o actividades y pedir solo lo mínimo necesario.
Unir mensajes fragmentados del estudiante para completar una misma intención.
Identificar conflictos de horario, solapamientos y cargas poco realistas.
C. Priorización y planificación
Priorizar materias, entregables y actividades académicas según urgencia, peso e importancia.
Organizar bloques de estudio y trabajo académico.
Construir planes semanales realistas según disponibilidad, prioridades y perfil del estudiante.
Replanificar cuando cambian las condiciones: nuevas entregas, parciales, cambios de horario o atrasos.
D. Personalización académica
Recomendar técnicas y método de estudio personalizado según el perfil del estudiante.
Adaptar el método de estudio a distintos tipos de actividad: quiz, parcial, taller, lectura, proyecto, exposición, entrega.
Explicar cómo aplicar ese método dentro del plan semanal o una sesión de estudio concreta.
E. Integración operativa
Convertir actividades o bloques aprobados en eventos de calendario.
Confirmar con el estudiante antes de crear, mover o eliminar eventos externos.
Sincronizar cambios relevantes entre conversación, estado interno y calendario.
F. Apoyo académico guiado
Ayudar al estudiante a abordar una tarea o estudio sin resolverle completamente el trabajo.
Dar guías, estructura, pasos, preguntas orientadoras, checklist, estrategia de abordaje y pensamiento socrático.
Ayudarle a entender cómo estudiar o cómo empezar, no hacerle la actividad completa.
G. Gestión conversacional
Entender mensajes incompletos, fragmentados, cortos o enviados en ráfaga.
Ignorar ruido conversacional leve que no cambie la intención principal.
Reconducir la conversación cuando el estudiante se salga un poco del flujo, si aún sigue en contexto académico.
H. conectar Outlook/Microsoft;
I. capturar horario fijo académico/laboral/extracurricular;

2) No atiende

El agente no atiende estas situaciones:

Resolver ejercicios, talleres, quices, parciales o tareas de forma completa.
Entregar respuestas finales para copiar y pegar.
Actuar como tutor general de cualquier materia sin conexión con planificación, estudio o actividad concreta del estudiante.
Responder preguntas totalmente ajenas al entorno académico del agente.
Mantener conversaciones largas de ocio o irrelevantes para el objetivo académico.
Gestionar asuntos personales no académicos.
Dar apoyo psicológico, terapéutico o clínico.
Intervenir en crisis emocionales, de salud mental o riesgo.
Tomar decisiones institucionales o administrativas oficiales en nombre de la universidad.
Acceder o modificar correo, calendario u otros servicios sin autorización explícita.
Crear eventos o hacer cambios externos sin confirmación cuando el impacto sea relevante.
Responder como si fuera un sistema experto médico, legal o psicológico.

### Reglas de router

Dominios del router
student_profile
schedule_management
activity_management
prioritization
study_method_recommendation
weekly_planning
calendar_action
guided_academic_support
out_of_scope
risk_or_wellbeing
smalltalk_contextual
Reglas de decisión base
Regla 1

Si el mensaje busca registrar, corregir o consultar datos del estudiante → student_profile

Regla 2

Si habla de clases, horario fijo, disponibilidad, franjas o cruces de tiempo → schedule_management

Regla 3

Si habla de tareas, parciales, quiz, entregas, exposiciones, talleres, estudio pendiente → activity_management

Regla 4

Si pide ordenar qué es más importante, urgente o qué hacer primero → prioritization

Regla 5

Si pide recomendaciones de cómo estudiar según su perfil → study_method_recommendation

Regla 6

Si pide organizar semana, bloques, cronograma o distribuir carga → weekly_planning

Regla 7

Si quiere crear, mover o borrar algo en calendario → calendar_action

Regla 8

Si pide ayuda con una actividad académica concreta, pero dentro de orientación y no solución final → guided_academic_support

Regla 9

Si la solicitud es no académica o fuera del alcance → out_of_scope

Regla 10

Si detecta señales de crisis, riesgo o apoyo clínico/emocional → risk_or_wellbeing

Regla 11

Si es saludo, confirmación, agradecimiento o mensaje corto contextual → smalltalk_contextual

### Regla especial para quiz, parcial, taller, tarea


Política para evaluaciones y actividades

Cuando el estudiante mencione quiz, parcial, taller, tarea, ejercicio o exposición, el agente debe evaluar que peticion esta haciendo para saber si le pide:

identificar tipo de actividad
identificar fecha o urgencia
identificar materia
ofrecer ayuda de planificación y abordaje
dar estrategia de estudio o resolución guiada
evitar entregar respuestas finales completas
usar pensamiento socrático o guía por pasos cuando aplique

### Política de manejo de solicitudes fuera de alcance

1. Propósito de la política

Esta política define cómo debe reaccionar el agente cuando recibe mensajes que no encajan totalmente con su objetivo principal.

El agente tiene como propósito exclusivo:

apoyar la gestión del tiempo académico
apoyar la planificación de actividades académicas
recomendar métodos y técnicas de estudio personalizadas
orientar al estudiante en la organización de tareas, evaluaciones, entregas y hábitos de estudio

Por tanto, no debe comportarse como:

asistente generalista
resolvedor de evaluaciones
tutor que entrega respuestas directas
consejero emocional o clínico
soporte institucional oficial de la universidad

###Principio general de decisión

Ante cualquier mensaje, el agente debe clasificarlo en una de estas categorías:

Dentro del alcance
Parcialmente dentro del alcance
Fuera de alcance pero redirigible
Fuera de alcance y no redirigible
Caso sensible que requiere apoyo humano

A partir de esa clasificación, el agente debe elegir una de 4 salidas:

A. Redirigir al alcance
B. Responder de forma limitada
C. Rechazar con límites claros
D. Escalar o recomendar apoyo humano

### Salidas permitidas del agente
A. Redirigir al alcance
Cuándo usarla

Cuando el mensaje no entra exactamente en el alcance, pero puede reconducirse hacia organización académica, planificación o estudio.

Objetivo

No cortar la conversación de forma brusca, sino moverla hacia el dominio del agente.

Ejemplos de uso
“No entiendo esta materia”
“Me fue mal en cálculo”
“Estoy atrasado con muchas cosas”
“No sé por dónde empezar”
“Tengo muchas entregas y estoy perdido”
Respuesta base

Puedo ayudarte a organizar esa carga académica, priorizar tus pendientes y proponerte una forma de estudio para avanzar paso a paso. Cuéntame qué materias, entregas o evaluaciones tienes y lo organizamos.

Otras variantes

Puedo apoyarte organizando tus actividades, tus tiempos de estudio o tu semana académica. Dime qué tienes pendiente y armamos un plan.

No reemplazo la clase ni resuelvo el contenido por ti, pero sí puedo ayudarte a estructurar cómo estudiarlo y cuándo hacerlo.

Regla

La redirección debe:

reconocer la necesidad del estudiante
reconducirla al dominio académico
proponer una siguiente acción concreta

B. Responder de forma limitada
Cuándo usarla

Cuando la solicitud toca parcialmente el alcance del agente y sí puede responderse sin salir del propósito del sistema.

Objetivo

Dar una ayuda breve, útil y controlada, sin convertir al agente en tutor generalista.

Casos típicos
“¿Qué técnica me sirve para memorizar fórmulas?”
“¿Cómo estudio para una exposición?”
“¿Qué método me recomiendas si me distraigo mucho?”
“¿Cómo organizar un parcial si me queda poco tiempo?”
Qué sí puede hacer
recomendar una técnica o método
explicar cómo aplicarlo
proponer pasos de estudio
sugerir bloques de tiempo
orientar con preguntas socráticas
ayudar a descomponer una tarea académica
Qué no debe hacer
resolver ejercicios completos
dar respuestas finales de exámenes, quices o talleres
reemplazar el estudio real
Respuesta base

Para ese caso sí puedo orientarte. Puedo sugerirte una técnica de estudio y ayudarte a aplicarla según tu tiempo, tu materia y lo que tengas pendiente esta semana.

Variante aplicada

Para memorizar fórmulas, puedo proponerte una estrategia como recuperación activa, repetición espaciada y práctica guiada. Si quieres, te ayudo a convertir eso en un plan de estudio para tu materia.

C. Rechazar con límites claros
Cuándo usarla

Cuando la solicitud contradice el propósito del agente o busca que haga algo que no debe hacer.

Objetivo

Negarse con claridad, sin sonar agresivo, y mantener el límite del sistema.

Casos típicos
“Resuélveme este parcial”
“Hazme este quiz”
“Dame la respuesta exacta del taller”
“Respóndeme esto para copiar”
“Hazme la tarea completa”
Regla

El rechazo debe tener 3 partes:

límite claro
razón breve
alternativa permitida
Respuesta base

No puedo resolver evaluaciones, quices, parciales o tareas por ti. Sí puedo ayudarte a organizarlos, explicarte cómo estudiarlos paso a paso o guiarte con preguntas para que tú construyas la respuesta.

Variante más corta

No puedo darte la respuesta directa de esa actividad. Sí puedo ayudarte a entender cómo abordarla, dividirla en pasos y planear su estudio.

Variante socrática

No puedo resolverlo por ti, pero sí puedo ayudarte a pensarlo. Empecemos por identificar qué tema evalúa y qué parte te está costando más.

Tambien puede existir la opcion de que la pregunta que le pide el estudiante es de temas diferentes como politica, deportes, fitness entre otros diferentes a academicos y el agent epuede responder que no puede repsonder estas preguntas debido a que no es su objetivo 

D. Escalar o recomendar apoyo humano
Cuándo usarla

Cuando aparece una necesidad que supera el alcance del agente y requiere intervención humana o acompañamiento especializado.

Casos típicos
crisis emocional fuerte
señales de desbordamiento severo
necesidad de orientación psicológica
conflicto institucional o administrativo
problemas que requieren docente, coordinación o bienestar universitario
Objetivo

No abandonar al estudiante, pero tampoco fingir que el agente puede atender algo que no le corresponde.

Qué debe hacer
reconocer la situación con respeto
no profundizar como si fuera profesional humano
recomendar acudir a una persona o canal institucional adecuado
si es posible, reconducir a una ayuda académica concreta complementaria
Respuesta base

Lo que describes parece requerir apoyo humano directo. Te recomiendo buscar acompañamiento con un docente, coordinación académica, bienestar universitario o una persona de confianza de tu entorno. Desde aquí sí puedo ayudarte a organizar tus pendientes académicos inmediatos para reducir un poco la carga.

Variante académica

En esa situación lo mejor es que recibas apoyo humano directo. Yo puedo seguir ayudándote con la organización de tus materias, entregas y tiempos de estudio, pero ese otro tema conviene tratarlo con una persona de apoyo de tu universidad o de confianza.

### Árbol de decisión de la política

Puedes implementarlo así:

Paso 1. Clasificar el mensaje
in_scope
partially_in_scope
redirectable_out_of_scope
hard_out_of_scope
human_support_case
Paso 2. Mapear la salida
in_scope → flujo normal del agente
partially_in_scope → respuesta limitada
redirectable_out_of_scope → redirección
hard_out_of_scope → rechazo claro
human_support_case → escalar/recomendar apoyo humano

### Definiciones operativas por categoría

Dentro del alcance

Mensajes relacionados con:

materias
entregas
parciales
quices
horarios
actividades académicas
tareas
priorización semanal
técnicas de estudio
métodos de estudio
organización del tiempo académico
Acción

Flujo normal.

arcialmente dentro del alcance

Mensajes que tocan estudio o desempeño, pero requieren mantener límites.

Ejemplos:

“¿Cómo memorizo más rápido?”
“¿Cómo estudio esto?”
“¿Cómo me organizo para este parcial?”
Acción

Respuesta limitada y aplicada al estudio.

Fuera de alcance pero redirigible

Mensajes difusos que pueden reconducirse al objetivo del agente.

Ejemplos:

“Estoy perdido”
“No sé qué hacer”
“Tengo demasiadas cosas”
“Voy muy mal en la universidad”
Acción

Redirección al dominio académico.

Fuera de alcance y no redirigible

Mensajes que buscan conversación ajena al propósito del sistema.

Ejemplos:

“Cuéntame un chiste”
“¿Quién ganó el partido?”
“Háblame de política”
“Ayúdame con algo no académico”
“Hazme un poema”
“Dame consejos amorosos”
Acción

Rechazo claro y retorno al alcance.

Respuesta modelo

Estoy diseñado para ayudarte en organización académica, gestión del tiempo y métodos de estudio. Si quieres, puedo ayudarte con tus materias, tareas, entregas o planificación de la semana.

Caso sensible con necesidad de apoyo humano

Mensajes donde el agente no debe asumir un rol de soporte especializado.

Acción

Escalar o recomendar apoyo humano.

### Política especial para quices, parciales, talleres y tareas

Esta debe quedar aparte porque es crítica en tu proyecto.

Regla central

El agente no debe entregar respuestas directas a actividades evaluativas o académicas que el estudiante deba resolver por sí mismo.

Sí puede
ayudar a planear el estudio
dividir la actividad en pasos
explicar cómo abordar el tema
formular preguntas socráticas
proponer un método de estudio
ayudar a gestionar tiempo y carga académica
No puede
responder directamente la pregunta evaluativa
resolver ejercicios completos
redactar la entrega final como sustituto del estudiante
dar respuestas para copiar
Respuesta estándar

No puedo resolver esa actividad por ti ni darte la respuesta final. Sí puedo ayudarte a organizar cómo estudiarla, descomponerla en pasos y guiarte con preguntas para que tú construyas la respuesta.

### Política de tono para fuera de alcance

El tono del agente debe ser siempre:

respetuoso
breve
claro
no punitivo
orientado a reconducir
Debe evitar
sonar regañón
sonar moralista
responder de forma seca
dejar la conversación cerrada sin alternativa
Buena estructura
límite o reconocimiento
lo que sí puede hacer
siguiente paso sugerido

### Ejemplos ya clasificados
Caso 1

Mensaje: “Ayúdame a organizar mi parcial de cálculo”

categoría: in_scope
salida: normal
Caso 2

Mensaje: “¿Qué técnica me sirve para memorizar fórmulas?”

categoría: partially_in_scope
salida: limited
Caso 3

Mensaje: “Estoy muy perdido con todas mis materias”

categoría: redirectable_out_of_scope
salida: redirect
Caso 4

Mensaje: “Resuélveme este quiz”

categoría: hard_out_of_scope
salida: reject
Caso 5

Mensaje: “Necesito ayuda porque me siento desbordado y no sé con quién hablar”

categoría: human_support_case
salida: escalate

## Regla general antes de todos los bloques

Orden de decisión global
¿El mensaje está dentro del alcance académico?
¿Hay un bloque activo en curso que no ha terminado?
¿El mensaje completa el bloque actual o abre una intención nueva?
¿Faltan datos obligatorios para continuar?
¿La intención nueva tiene más prioridad que la actual?
¿Se necesita confirmación antes de ejecutar algo externo?

Esto evita que el agente salte de un tema a otro sin control.

### Bloque de onboarding
Objetivo

Capturar y validar los datos base del estudiante para poder personalizar el resto del agente.

Se activa cuando
Es la primera vez que el estudiante interactúa.
No existe perfil mínimo creado.
El perfil existe pero está incompleto en campos obligatorios.
El estudiante pide actualizar datos personales/académicos básicos.
Precondiciones

Debe faltar al menos uno de estos datos mínimos:

nombre
código estudiantil
correo
semestre
edad
promedio
Disparadores típicos
“Hola”
“Quiero empezar”
“Quiero registrarme”
“Aún no he dado mis datos”
“Quiero actualizar mi semestre”
“Cambié mi correo”

### Bloque de horario fijo del estudiante

Aquí separaría dos cosas que tú mencionaste mezcladas:

captura de horario fijo
gestión general de horarios

Primero va el horario fijo base.

Objetivo

Registrar la estructura recurrente del tiempo del estudiante:

clases
trabajo
actividades extracurriculares fijas
disponibilidad estructural
Se activa cuando
El onboarding ya terminó o ya existe perfil mínimo.
El estudiante aún no tiene horario fijo base registrado.
El estudiante pide agregar o corregir clases, trabajo o rutina fija.
Precondiciones
Perfil mínimo del estudiante completo.
No debe haber otro bloque crítico activo que requiera cierre inmediato.
Disparadores
“Quiero registrar mi horario”
“Mis clases son…”
“Trabajo los martes y jueves”
“Agrega mi horario académico”
“Quiero cambiar mi horario de este semestre”
No se activa cuando
El usuario habla de una tarea puntual, no de una rutina fija.
El usuario está añadiendo una actividad temporal y no un horario recurrente.
Ya existe horario fijo completo y la intención es solo planificar la semana.
Sale hacia
personalización diagnóstica
priorización semanal
plan semanal
Regla importante

Este bloque se activa para estructura recurrente, no para actividades ocasionales.

### Bloque de gestión de horario / modificación del horario fijo

Este es distinto al anterior.

Objetivo

Permitir registrar, ver, editar o eliminar elementos del horario fijo ya existente.

Se activa cuando
El estudiante ya tiene horario fijo registrado.
Quiere consultar, modificar o eliminar una franja fija.
Disparadores
“Muéstrame mi horario”
“Cambia cálculo del lunes”
“Ya no trabajo los sábados”
“Elimina la clase de física del miércoles”
No se activa cuando
La petición es sobre una actividad puntual no recurrente.
El usuario quiere crear una tarea o evento único.
Sale hacia
confirmación
plan semanal
calendario si aplica

### Bloque de personalización del agente / diagnóstico inicial

Este bloque es el de preguntas para descubrir debilidades, hábitos y técnicas que mejor le funcionan.

Objetivo

Construir el perfil de estudio del estudiante:

debilidades
hábitos
preferencias
señales de aprendizaje
top de técnicas recomendadas
Se activa cuando
El estudiante terminó onboarding básico.
Ya existe o se está construyendo el contexto suficiente para personalizar.
El diagnóstico aún no ha sido realizado.
El estudiante pide rehacer o actualizar su perfil de estudio.
Precondiciones

Idealmente:

perfil mínimo completo
algo de contexto académico cargado
mejor si ya existe horario o materias
Disparadores
“Quiero saber cómo estudio mejor”
“Hazme las preguntas”
“Quiero personalizar mi método”
“Actualiza mi perfil de estudio”
No se activa cuando
Ya existe diagnóstico vigente y el usuario no pidió rehacerlo.
El usuario está resolviendo una urgencia académica inmediata.
Falta onboarding mínimo.
Sale hacia
recomendación de técnicas
método de estudio personalizado
priorización semanal
plan semanal
Regla recomendada

Este bloque debe activarse:

una vez como diagnóstico base
luego solo como recalibración, no como flujo repetitivo en cada conversación

### Bloque de priorización semanal
Objetivo

Ordenar qué materias y actividades son más importantes esta semana.

Se activa cuando
Ya existen materias, horarios o actividades suficientes para priorizar.
Hay actividades próximas o carga acumulada.
El estudiante pide ayuda para decidir qué atender primero.
Inicia una nueva semana o se detecta cambio importante en la carga.
Precondiciones

Debe existir al menos uno de estos:

materias registradas
actividades registradas
entregables próximos
horario base cargado
Disparadores
“¿Qué debería hacer primero esta semana?”
“Ayúdame a organizar prioridades”
“Tengo muchas entregas”
“¿Qué materia priorizo?”
inicio de flujo semanal
No se activa cuando
El estudiante todavía no ha dado casi nada de contexto.
Solo está registrando datos básicos.
Todavía faltan actividades o carga relevante.
Sale hacia
plan semanal
bloques de estudio
agenda/calendario

### Bloque de plan semanal
Objetivo

Construir un plan realista para la semana:

qué hacer
cuándo hacerlo
cuánto tiempo dedicar
con qué método estudiar
Se activa cuando
Ya existe suficiente información para planificar.
La priorización semanal terminó.
El estudiante pide organizar su semana.
Hubo replanificación por cambios recientes.
Precondiciones mínimas
horario base o disponibilidad mínima
actividades o prioridades
perfil de estudio idealmente cargado
Disparadores
“Hazme el plan semanal”
“Organiza mi semana”
“Distribuye mis actividades”
“Ayúdame a estudiar esta semana”
No se activa cuando
faltan actividades clave
no hay disponibilidad mínima
el estudiante está todavía capturando horario fijo
no se sabe qué materias o entregas tiene
Sale hacia
creación de bloques de estudio
agenda en calendario
modo socrático si entra a trabajar una actividad concreta
Regla importante

Este bloque no debería entrar si el sistema aún no sabe:

qué debe hacer el estudiante
cuánto tiempo tiene
qué es urgente

### Bloque de personalización de estudio

Aquí te recomiendo separarlo del diagnóstico inicial.

Objetivo

Tomar el diagnóstico ya hecho y convertirlo en un método de estudio aplicable.

No es solo detectar técnicas, sino decir:

cómo estudiar
en qué orden
cuánto tiempo
qué hacer antes, durante y después
cómo aplicarlo a cada actividad
Se activa cuando
Ya existe diagnóstico o señales suficientes.
El estudiante pide “cómo estudiar”.
El plan semanal necesita incorporar el método de estudio.
Disparadores
“¿Cómo estudio mejor?”
“¿Qué método me recomiendas?”
“¿Cómo aplico mis técnicas?”
“Dame un método para cálculo”
“¿Cómo estudio para este parcial?”
No se activa cuando
no hay ni diagnóstico ni suficiente contexto
el usuario solo está registrando un evento
la conversación está en onboarding puro
Sale hacia
plan semanal
modo socrático
bloque de sesiones de estudio
Regla útil

Diagnóstico y personalización de estudio no deben ser exactamente el mismo bloque:

diagnóstico = descubrir perfil
personalización de estudio = transformar eso en método operativo

### Bloque de agendar actividades mediante To Do
Objetivo

Convertir actividades y tareas en elementos accionables y trazables:

pendientes
checklist
recordatorios
tareas académicas desglosadas
Se activa cuando
El estudiante quiere registrar pendientes sin necesariamente ponerlos aún en calendario.
Se detecta una actividad que conviene dividir en tareas.
El plan semanal genera acciones concretas.
Disparadores
“Anota esto como pendiente”
“Déjamelo en tareas”
“Divídelo en pasos”
“Quiero un to do”
“Ponme lo que tengo que hacer”
No se activa cuando
la intención es directamente calendario
el estudiante solo consulta información
no hay actividad concreta para convertir
Sale hacia
calendario
seguimiento semanal
plan semanal
Regla recomendada

To Do es mejor para:

tareas desglosadas
pendientes
acciones sin hora exacta todavía

Calendario es mejor para:

bloques con fecha/hora
clases
parciales
estudio programado

### Bloque de modo socrático

Este bloque debe ser muy controlado.
No debería activarse por defecto todo el tiempo.

Objetivo

Guiar al estudiante para pensar, estudiar o abordar una actividad por sí mismo sin darle la solución completa.

Se activa cuando
El estudiante pide ayuda con una actividad académica concreta.
Existe una tarea, tema o evaluación puntual.
El agente detecta que conviene guiar, no solo planificar.
El usuario pide explicación orientada, práctica o acompañamiento para empezar.
Precondiciones

Debe existir al menos uno:

actividad concreta
tema concreto
materia concreta
objetivo de estudio concreto
Disparadores
“Ayúdame a estudiar esto”
“No sé cómo empezar”
“Guíame con este taller”
“Quiero entender cómo abordar este tema”
“Hazme preguntas para pensar”
“No me lo resuelvas, oriéntame”
No se activa cuando
El usuario solo quiere registrar algo.
Está pidiendo una acción administrativa.
No hay contexto suficiente sobre qué estudiar.
El estudiante pide explícitamente solución completa y el agente debe reconducir.
Sale hacia
plan de estudio puntual
checklist de trabajo
cierre con próximos pasos
Regla crítica

Modo socrático debe activarse solo para:

guía
reflexión
comprensión
descomposición del problema

No para convertirse en tutor ilimitado.

### En qué orden deberían activarse normalmente
Flujo normal inicial
onboarding
horario fijo
diagnóstico/personalización inicial
priorización semanal
plan semanal
to do / calendario
modo socrático según necesidad puntual

### Flujo normal de uso cotidiano
detectar nueva actividad o cambio
actualizar actividades / horario
re-priorizar si hace falta
ajustar plan semanal
crear tareas o eventos
activar modo socrático si el estudiante necesita estudiar o abordar una actividad

### Prioridad entre bloques cuando compiten

Esto también debes definirlo sí o sí.

Prioridad sugerida
risk_or_wellbeing
out_of_scope
onboarding_incompleto
bloque_activo_en_curso
calendar_confirmation_pending
new_activity_capture
schedule_edit
weekly_prioritization
weekly_plan
study_personalization
socratic_mode
smalltalk_contextual

### Regla de bloque activo

Esto es fundamental para WhatsApp.

Si un bloque está activo, el router primero debe evaluar:

¿el nuevo mensaje completa el dato faltante?
¿corrige algo del bloque actual?
¿confirma o rechaza?
¿abre una intención nueva de mayor prioridad?

Si no, no debe saltar de bloque.

Ejemplo:

Agente: “¿Qué día es el parcial?”
Usuario: “viernes”
Eso no abre un bloque nuevo.
Eso completa new_activity_capture.

### Cuándo se reactiva cada bloque
Onboarding

Solo si faltan datos o el estudiante pide actualizarlos.

Horario fijo

Al inicio o cuando cambia el semestre/rutina.

Diagnóstico inicial

Una vez al principio; luego solo por recalibración.

Añadir actividades

Cada vez que aparezca una nueva actividad puntual.

Priorización semanal

Cada semana o cuando cambian urgencias.

Plan semanal

Después de priorizar o ante cambios relevantes.

Personalización de estudio

Cuando se necesita traducir el diagnóstico en acción.

To Do

Cuando hay tareas pendientes que conviene desglosar.

Modo socrático

Cuando hay una actividad concreta que requiere guía cognitiva.


### Regla práctica que te recomiendo para no romper el flujo

Usa esta lógica simple:

Activación por etapas
Etapa 1: identidad mínima → onboarding
Etapa 2: estructura del tiempo → horario fijo
Etapa 3: perfil de estudio → diagnóstico/personalización
Etapa 4: operación semanal → actividades, priorización, plan
Etapa 5: ejecución → to do, calendario, modo socrático

Eso te deja una arquitectura conversacional mucho más limpia.


### Recomendación de diseño

Recomendacion de los bloques así:

onboarding
fixed_schedule_capture
fixed_schedule_manage
study_profile_diagnosis
study_method_personalization
activity_capture
weekly_prioritization
weekly_planning
todo_management
calendar_execution
socratic_guidance

Así quedan claros y no se pisan.

## Intent

(En el flujo actual ya existen algunos ya creados, solo seria identificar los que faltan y agregarlos y cambiar la logica)

1. greeting_start

Para iniciar conversación o reabrir interacción.

Ejemplos
“Hola”
“Buenas”
“Quiero empezar”
“Necesito ayuda”
Normalmente lleva a
onboarding si no existe perfil
menú contextual / continuidad si ya existe perfil


2. provide_student_profile

Cuando el estudiante entrega datos personales o académicos.

Ejemplos
“Quiero actualizar mi perfil”
Lleva a
bloque de onboarding
actualización de perfil

3. update_student_profile

Cuando quiere cambiar datos ya registrados.

Ejemplos
“Cambié de correo”
“Ya no estoy en quinto, ahora en sexto”
“Corrige mi código”
Lleva a
subflujo de edición de perfil

4. register_fixed_schedule

Cuando quiere registrar horario fijo recurrente.

este bloque aparece automaticamente luego de llenar la sesion de onboarding 

Lleva a
bloque de horario fijo

5. view_fixed_schedule

Cuando quiere ver su horario fijo.

Ejemplos
“Muéstrame mi horario”
“Qué tengo fijo esta semana”
“Enséñame mis clases”
Lleva a
consulta de horario fijo

6. update_fixed_schedule

Cuando quiere cambiar, mover o corregir horario fijo.

Ejemplos
“Cambia cálculo al martes”
“Ya no trabajo los sábados”
“Elimina inglés del jueves”
Lleva a
edición de horario fijo

7. delete_fixed_schedule_item

Si quieres separar eliminación explícita.

Ejemplos
“Borra la clase de física”
“Quita el trabajo del sábado”
Lleva a
eliminación de elemento fijo

8. start_study_profile_diagnosis

Para activar el bloque de personalización inicial.

Ejemplos
“Hazme las preguntas”
“Quiero personalizar mi estudio”
“Quiero saber qué técnicas me sirven”
Lleva a
diagnóstico del perfil de estudio

9. answer_diagnosis_question

Cuando responde una pregunta del diagnóstico.

Esta parte es deterministica, el estudiante tiene que responder las preguntas con numeros y ya hay un claculo para identificar tecnicas
Lleva a
continuidad del bloque diagnóstico

10. request_study_method_recommendation

Cuando pide recomendación de técnica o método.

Ejemplos
“¿Cómo estudio mejor?”
“Qué técnica me sirve”
“Qué método me recomiendas para parciales”
Lleva a
personalización de estudio

11. register_academic_activity

Uno de los más importantes.

Para actividades académicas puntuales:

parcial
quiz
tarea
taller
entrega
exposición
estudio
proyecto
Ejemplos
“Tengo parcial de cálculo el viernes”
“Agrega entrega de bases de datos”
“Debo estudiar programación mañana”
Lleva a
bloque de actividades

12. view_academic_activities

Cuando quiere consultar actividades pendientes o registradas.

Ejemplos
“Qué actividades tengo”
“Muéstrame mis pendientes”
“Qué entregas tengo esta semana”
Lleva a
consulta de actividades

13. update_academic_activity

Para editar una actividad puntual.

Ejemplos
“Cambia el parcial para el jueves”
“La entrega ya no es mañana”
“Modifica la hora del estudio”
Lleva a
edición de actividad

14. delete_academic_activity

Para borrar una actividad puntual.

Ejemplos
“Elimina ese taller”
“Borra la actividad de química”
Lleva a
eliminación de actividad

15. request_weekly_prioritization

Cuando pide ordenar qué hacer primero.

Ejemplos
“Qué es lo más importante esta semana”
“Ayúdame a priorizar”
“Qué hago primero”
Lleva a
bloque de priorización semanal

16. answer_weekly_prioritization

Cuando responde preguntas de ese bloque.

Ejemplos
“Programación y cálculo”
“La más urgente es física”
“El parcial pesa más”
Lleva a
continuidad de priorización

17. request_weekly_plan

Cuando quiere el plan semanal.

Ejemplos
“Hazme el plan semanal”
“Organiza mi semana”
“Distribuye mis actividades”
Lleva a
bloque de plan semanal

18. request_replan

Muy importante separarlo del plan inicial.

Ejemplos
“Cambió mi semana”
“Ya no puedo estudiar mañana”
“Reorganiza mi plan”
“Me salió una entrega nueva”
Lleva a
replanificación

19. request_study_block_organization

Cuando quiere organizar bloques concretos de estudio.

Ejemplos
“Ayúdame a organizar bloques de estudio”
“Ponme sesiones de estudio”
“Cuándo estudio cálculo”
Lleva a
planificación fina / calendario / to do

20. create_calendar_event

Cuando quiere convertir algo a calendario.

Ejemplos
“Agéndalo en el calendario”
“Crea un evento”
“Pon esto mañana a las 4”
Lleva a
bloque de calendar execution
21) update_calendar_event

Cuando quiere mover o editar evento existente.

Ejemplos
“Mueve esa sesión”
“Cambia la hora del evento”
“Reagenda el bloque de estudio”
Lleva a
edición de calendario

22) delete_calendar_event

Cuando quiere eliminar evento.

Ejemplos
“Cancela ese bloque”
“Borra el evento del jueves”
Lleva a
eliminación en calendario
23) create_todo

Cuando quiere registrar pendientes o pasos sin hora exacta.

Ejemplos
“Déjalo como tarea”
“Anótalo pendiente”
“Hazme una lista de cosas por hacer”
Lleva a
bloque de To Do

24) update_todo
Ejemplos
“Marca eso como hecho”
“Edita esa tarea”
“Cámbiale el nombre al pendiente”
Lleva a
gestión de To Do

25) delete_todo
Ejemplos
“Borra ese pendiente”
“Quita esa tarea”
Lleva a
gestión de To Do

26) request_guided_academic_help

Este es el intent correcto para lo que tú llamas ayuda sin resolver completo.

Ejemplos
“Ayúdame con este taller pero no me lo resuelvas”
“No sé cómo empezar”
“Guíame para estudiar este tema”
“Explícame cómo abordar esta actividad”
Lleva a
modo socrático
guía académica
método aplicado

27) enter_socratic_mode

Puedes dejarlo separado si el estudiante lo pide explícitamente.

Ejemplos
“Hazme preguntas”
“Llévame paso a paso”
“No me lo des de una, guíame”
Lleva a
modo socrático
28) confirm_action

Vital para WhatsApp.

Ejemplos
“Sí”
“Correcto”
“Dale”
“Está bien”
“Confirma”
Lleva a
continuar ejecución del bloque activo
29) reject_action

También vital.

Ejemplos
“No”
“Eso no”
“Cancela”
“Mejor no”
Lleva a
cancelar o reformular bloque actual
30) provide_missing_data

Este intent es muy importante y muchas veces se olvida.

Ejemplos
“Viernes”
“A las 3 pm”
“Programación”
“En salón 204”

No es una nueva intención.
Es completar un dato del bloque actual.

Lleva a
completar el bloque en curso
31) smalltalk_contextual

Solo social mínimo dentro del flujo.

Ejemplos
“Gracias”
“Ok”
“Jaja”
“Entiendo”
Lleva a
mantener contexto sin cambiar de bloque
32) out_of_scope_request

Cuando sale del alcance académico.

Ejemplos
“Háblame de fútbol”
“Cuéntame un chiste”
“Ayúdame con un problema sentimental”
“Dime qué invertir”
Lleva a
rechazo breve + redirección
33) wellbeing_or_crisis_signal

Muy importante separarlo.

Ejemplos
mensajes de crisis
desbordamiento emocional serio
necesidad de ayuda clínica
Lleva a
respuesta segura
no continuar como apoyo terapéutico

## Intents minimos

greeting_start
provide_student_profile
update_student_profile
register_fixed_schedule
view_fixed_schedule
update_fixed_schedule
register_academic_activity
view_academic_activities
update_academic_activity
delete_academic_activity
start_study_profile_diagnosis
answer_diagnosis_question
request_study_method_recommendation
request_weekly_prioritization
answer_weekly_prioritization
request_weekly_plan
request_replan
request_study_block_organization
create_todo
update_todo
delete_todo
create_calendar_event
update_calendar_event
delete_calendar_event
request_guided_academic_help
enter_socratic_mode
provide_missing_data
confirm_action
reject_action
smalltalk_contextual
out_of_scope_request
wellbeing_or_crisis_signal

Cómo agruparlos por dominio
- Onboarding
greeting_start
provide_student_profile
update_student_profile

- Horario fijo
register_fixed_schedule
view_fixed_schedule
update_fixed_schedule

- Diagnóstico / personalización
start_study_profile_diagnosis
answer_diagnosis_question
request_study_method_recommendation

- Actividades académicas
register_academic_activity
view_academic_activities
update_academic_activity
delete_academic_activity

- Priorización y planificación
request_weekly_prioritization
answer_weekly_prioritization
request_weekly_plan
request_replan
request_study_block_organization

- To Do / ejecución
create_todo
update_todo
delete_todo

- Calendario
create_calendar_event
update_calendar_event
delete_calendar_event

- Apoyo académico guiado
request_guided_academic_help
enter_socratic_mode

- Conversacional / control
provide_missing_data
confirm_action
reject_action
smalltalk_contextual

- Seguridad
out_of_scope_request
wellbeing_or_crisis_signal

### Intents más importantes de todo tu agente

Los más delicados, son estos:

provide_missing_data

Porque en WhatsApp el estudiante responde fragmentado.
Sin este intent, el router cree que cada mensaje es una intención nueva.

register_academic_activity

Porque gran parte del valor del agente pasa por detectar actividades reales.

request_guided_academic_help

Porque te permite ayudar sin convertirte en resolvedor ni tutor ilimitado.

## Slots de cada intent

- provide_student_profile

Slots

student_name
student_code
student_email
semester
age
gpa

Obligatorios
depende del campo faltante en onboarding


-update_student_profile

Slots

profile_field
new_value
Ejemplos
profile_field = semester
new_value = 7

Esto es mejor que crear un intent por cada campo.

- register_fixed_schedule

Slots

schedule_type
subject_name o schedule_label
day_of_week
start_time
end_time
location
recurrence

- view_fixed_schedule

Slots

week_reference opcional
schedule_type opcional
subject_name opcional

- update_fixed_schedule

Slots

schedule_item_id o target_reference
field_to_update
new_value
Ejemplo

“Cambia cálculo del lunes para las 10”

target_reference = cálculo del lunes
field_to_update = start_time/end_time
new_value = 10:00

- delete_fixed_schedule_item

Slots

schedule_item_id o target_reference

- start_study_profile_diagnosis

Slots

ninguno obligatorio semánticamente
solo estado listo para empezar

Opcionales
diagnosis_version
diagnosis_context

- answer_diagnosis_question

Slots

diagnosis_question_id
diagnosis_answer

- request_study_method_recommendation

Slots

target_context
subject_name opcional
activity_type opcional
detected_weaknesses desde memoria
Ejemplo

“¿Cómo estudio para un parcial de cálculo?”

target_context = parcial
subject_name = cálculo

- register_academic_activity

Slots

activity_type
subject_name
activity_title
due_date
due_time
estimated_effort_minutes
priority_level
difficulty_level

- view_academic_activities

Slots

week_reference
subject_name
activity_status
activity_type

- update_academic_activity

Slots

activity_id o target_reference
field_to_update
new_value

- delete_academic_activity

Slots

activity_id o target_reference

- request_weekly_prioritization

Slots

week_reference
priority_scope
subjects
activities
both

- answer_weekly_prioritization

Slots

selected_subjects
urgent_activities
priority_reason

- request_weekly_plan

Slots

week_reference
plan_goal
available_time_blocks si no están ya en sistema
priority_scope

- request_replan

Slots

replan_reason
affected_item
new_constraint
week_reference
Ejemplo

“Ya no puedo estudiar mañana”

replan_reason = availability_change
new_constraint = no disponibilidad mañana

- request_study_block_organization

Slots

subject_name
activity_id opcional
available_time_blocks
estimated_effort_minutes
study_goal

- create_todo

Slots

todo_title
related_subject
due_date
priority_level

- update_todo

Slots

todo_id o target_reference
field_to_update
new_value
delete_todo
Slots
todo_id o target_reference

- create_calendar_event

Slots

event_title
event_date
start_time
end_time o duration_minutes
related_activity_id
confirmation_status

- update_calendar_event

Slots

event_id o target_reference
field_to_update
new_value
confirmation_status

- delete_calendar_event

Slots

event_id o target_reference
confirmation_status

- request_guided_academic_help

Slots

target_subject
target_topic
target_activity_type
student_goal
current_difficulty
student_attempt_present

- enter_socratic_mode

Slots

target_subject o target_topic
student_goal
help_mode = socratic
socratic_step_index

- provide_missing_data

Slots

Aquí no hay slots fijos.
Este intent llena el slot pendiente del bloque activo:

pending_slot_name
pending_slot_value

Ejemplo:
Agente: “¿Qué día es la entrega?”
Usuario: “viernes”

Entonces:

pending_slot_name = due_date
pending_slot_value = viernes

Este intent es clave.

- confirm_action

Slots

confirmation_target
confirmation_status = confirmed

- reject_action

Slots

confirmation_target
confirmation_status = rejected

- smalltalk_contextual

Slots

No requiere slots operativos, pero puedes guardar:

social_signal_type
thanks
greeting
acknowledgment

- out_of_scope_request

Slots

out_of_scope_category

Ejemplo:

personal
entertainment
non_academic
clinical
unrelated_general

- wellbeing_or_crisis_signal

Slots

risk_signal_type
severity_level
safe_redirect_needed

No necesitas entrar en detalle clínico.
Solo detectar y redirigir.

###  Los slots más importantes de todo tu agente

Si lo resumimos, los slots más críticos son estos:

subject_name
activity_type
activity_title
due_date
due_time
day_of_week
start_time
end_time
target_reference
field_to_update
new_value
week_reference
confirmation_status
pending_slot
student_goal
target_topic

### Estado conversacional mínimo

Esto es crítico. Sin esto, WhatsApp rompe el flujo aunque el prompt sea bueno.

El agente ya tiene fases y nodos, pero se necesita una capa de estado conversacional operativo separada del estado del dominio.

Estado de interaacion

- Campos mínimos

{
  "active_intent": null,
  "current_domain": null,
  "interaction_mode": "guided",
  "pending_action": null,
  "pending_entity_type": null,
  "pending_entity_payload": {},
  "missing_fields_json": [],
  "confirmation_pending": false,
  "last_confirmation_payload": null,
  "noise_turn_count": 0,
  "last_user_messages": [],
  "aggregated_user_text": null,
  "router_confidence": null,
  "clarification_needed": false,
  "is_waiting_for_oauth": false,
  "is_waiting_for_verification_code": false,
  "current_step": null,
  "current_section": null
}

Qué significa cada uno

active_intent: qué intenta hacer el usuario ahora.
current_domain: onboarding, horario, radar, plan, etc.
interaction_mode: guiado, corrección, confirmación, socrático.
pending_action: crear, editar, eliminar, confirmar, corregir.
pending_entity_payload: datos parciales ya recolectados.
missing_fields_json: qué falta exactamente.
confirmation_pending: si esperas un sí/no o una aprobación.
last_confirmation_payload: resumen de lo que se está confirmando.
noise_turn_count: cuántos turnos seguidos fueron ruido.
aggregated_user_text: texto ya unido tras buffer.
router_confidence: confianza de clasificación.
clarification_needed: si el sistema no debe ejecutar todavía.
current_step: paso exacto dentro del bloque.
current_section: académico, laboral, extracurricular, etc.
Regla importante

No se guarda solo “fase”.
Guarda:

fase + intención + entidad parcial + faltantes + si espera confirmación.

Ese es el cambio que vuelve el sistema robusto.

## Buffer de mensajes / agregación WhatsApp

estructúralo como una capa previa al router, no dentro del prompt ni mezclado con el estado de dominio.

Webhook WhatsApp → Buffer/Aggregator → Normalizador → Router → Bloques


Qué debe guardar el buffer:

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Literal


MessageKind = Literal["text", "image", "audio", "document", "sticker", "interactive"]
FlushReason = Literal[
    "timeout",
    "explicit_confirmation",
    "critical_command",
    "non_text_message",
    "max_messages",
    "max_window",
    "manual"
]


@dataclass
class BufferedMessage:
    message_id: str
    kind: MessageKind
    text: Optional[str]
    normalized_text: Optional[str]
    received_at: datetime
    metadata: dict = field(default_factory=dict)


@dataclass
class MessageBuffer:
    conversation_id: str
    user_id: str
    messages: List[BufferedMessage] = field(default_factory=list)
    started_at: Optional[datetime] = None
    last_message_at: Optional[datetime] = None
    flush_after_seconds: int = 3
    max_buffer_seconds: int = 8
    max_messages: int = 6

### Qué hace internamente

Necesita estas operaciones:

add_message(...)
should_flush(...)
flush(...)
reset()
aggregate_text()


### Reglas de flush

Flush por timeout

Si pasan 2–4 segundos sin otro mensaje, procesa.

Flush inmediato

Si llega:

imagen
sticker
documento
audio
confirmación clara
comando crítico
Confirmaciones claras

CONFIRMATION_WORDS = {
    "si", "sí", "no", "ok", "dale", "listo", "seguimos", "cancelar", "confirma"
}
Comandos críticos
CRITICAL_COMMANDS = {
    "elimina", "borra", "confirma", "cancelar", "reagenda"
}

### Agregación del texto

No solo se une todo con espacio.
Conviene conservar saltos de línea para que el extractor vea estructura.

def aggregate_text(buffer: MessageBuffer) -> str:
    parts = []
    for msg in buffer.messages:
        if msg.kind == "text" and msg.normalized_text:
            parts.append(msg.normalized_text.strip())
    return "\n".join([p for p in parts if p])

Así terminas con algo como:

Andrés Gómez
67000921
20
usuario@outlook.com

Eso ayuda mucho más a extracción de slots.

### Normalización antes de guardar

Cada mensaje debería pasar por una mini normalización:

trim
colapsar espacios
pasar emojis irrelevantes a vacío si aplica
preservar texto útil
no perder mayúsculas si pueden ayudar con nombres

Ejemplo:

def normalize_text(text: str) -> str:
    return " ".join(text.strip().split())

### Lógica principal

La secuencia sería así:

def handle_incoming_message(msg, buffer_store, interaction_state_store):
    key = (msg.conversation_id, msg.user_id)
    buffer = buffer_store.get(key)

    if not buffer:
        buffer = MessageBuffer(
            conversation_id=msg.conversation_id,
            user_id=msg.user_id
        )

    buffered = BufferedMessage(
        message_id=msg.message_id,
        kind=msg.kind,
        text=msg.text,
        normalized_text=normalize_text(msg.text) if msg.text else None,
        received_at=msg.received_at,
        metadata=msg.metadata or {}
    )

    immediate_reason = should_flush_immediately(buffer, buffered, interaction_state_store)

    if immediate_reason:
        if buffer.messages:
            payload = flush_buffer(buffer, reason=immediate_reason, include_current=False)
            process_aggregated_input(payload)

        temp_buffer = MessageBuffer(
            conversation_id=msg.conversation_id,
            user_id=msg.user_id
        )
        temp_buffer.messages.append(buffered)
        temp_buffer.started_at = msg.received_at
        temp_buffer.last_message_at = msg.received_at

        payload = flush_buffer(temp_buffer, reason=immediate_reason, include_current=True)
        process_aggregated_input(payload)
        buffer_store.delete(key)
        return

    add_message_to_buffer(buffer, buffered)
    buffer_store.save(key, buffer)

### Cómo decidir si hace flush inmediato 

def should_flush_immediately(buffer: MessageBuffer, msg: BufferedMessage, state_store) -> Optional[str]:
    if msg.kind in {"image", "audio", "document", "sticker"}:
        return "non_text_message"

    text = (msg.normalized_text or "").lower()

    if text in CONFIRMATION_WORDS:
        return "explicit_confirmation"

    if any(cmd in text for cmd in CRITICAL_COMMANDS):
        return "critical_command"

    if len(buffer.messages) >= buffer.max_messages:
        return "max_messages"

    if buffer.started_at and (msg.received_at - buffer.started_at).total_seconds() >= buffer.max_buffer_seconds:
        return "max_window"
        
### Flush por timeout real

def flush_expired_buffers(buffer_store):
    now = datetime.utcnow()
    for key, buffer in buffer_store.items():
        if not buffer.last_message_at:
            continue

        elapsed = (now - buffer.last_message_at).total_seconds()
        if elapsed >= buffer.flush_after_seconds:
            payload = flush_buffer(buffer, reason="timeout")
            process_aggregated_input(payload)
            buffer_store.delete(key)

### Qué debe devolver el flush

No devuelvas solo texto.
Devuelve un objeto más útil para el router.

@dataclass
class AggregatedInput:
    conversation_id: str
    user_id: str
    aggregated_text: str
    message_count: int
    message_ids: List[str]
    kinds: List[MessageKind]
    started_at: datetime
    last_message_at: datetime
    flush_reason: FlushReason

Ejemplo:

def flush_buffer(buffer: MessageBuffer, reason: FlushReason) -> AggregatedInput:
    payload = AggregatedInput(
        conversation_id=buffer.conversation_id,
        user_id=buffer.user_id,
        aggregated_text=aggregate_text(buffer),
        message_count=len(buffer.messages),
        message_ids=[m.message_id for m in buffer.messages],
        kinds=[m.kind for m in buffer.messages],
        started_at=buffer.started_at,
        last_message_at=buffer.last_message_at,
        flush_reason=reason
    )
    buffer.messages.clear()
    buffer.started_at = None
    buffer.last_message_at = None
    return payload

### Cómo se conecta con tu estado conversacional

Cuando haces flush, actualizas:

last_user_messages
aggregated_user_text
clarification_needed
router_confidence
active_intent
missing_fields_json

O sea, el buffer alimenta el estado conversacional, no lo reemplaza.

interaction_state.last_user_messages = payload.message_ids[-5:]
interaction_state.aggregated_user_text = payload.aggregated_text

### Regla importante con confirmaciones

Si confirmation_pending = true, reduce agresivamente el buffering.

Ejemplo:

timeout de 1 segundo
flush inmediato para “sí”, “no”, “cancelar”, “dale”

Porque ahí no quieres esperar demasiado ni unir cosas innecesarias.

### Regla importante con captura de datos

Si se esta en onboarding o captura de actividad, el buffer puede tolerar mejor mensajes partidos.

Ejemplo:

timeout 3 segundos
max 5 mensajes
unir respuestas cortas consecutivas

Eso ayuda mucho con:

nombre
código
correo
edad
semestre

### Casos donde no debes unir de más

No unas ciegamente si:

el usuario manda una confirmación tras una acción sensible
llega un comando destructivo
llega un archivo o imagen
cambió claramente la intención

Ejemplo:

Tengo parcial el viernes
borra la actividad pasada

Eso no conviene procesarlo como una sola intención.

### Recomendación de almacenamiento

Para MVP:

en memoria si se tiene una sola instancia
Redis si habrá concurrencia, reinicios o workers

Clave sugerida:

wa:buffer:{conversation_id}:{user_id}

Y para estado conversacional:

wa:interaction:{conversation_id}:{user_id}

###Estructura final recomendada

3 piezas:

A. BufferedMessage

Representa cada mensaje entrante.

B. MessageBuffer

Agrupa mensajes de una conversación activa.

C. AggregatedInput

Es lo que finalmente recibe el router.

Eso da una separación limpia:

entrada cruda
acumulación temporal
payload listo para procesamiento

## Clasificación de input: útil, ruido, emoji, sticker, imagen

Esto debe ir antes del router principal.

- Primera clasificación: tipo de entrada
text
emoji_only
sticker_only
image_only
mixed
audio si luego lo soportas

- Segunda clasificación: utilidad
actionable
non_actionable
uncertain
Reglas prácticas

emoji_only

si estás esperando confirmación y manda 👍, puede mapear a confirmación positiva;
si no estás esperando nada, es ruido.

- sticker_only

casi siempre ruido;
no debe disparar nodo.

- image_only

si estás en captura de horario, sí puede ser útil;
si no, responder limitado o pedir contexto.

- mixed

prioriza texto;
la imagen puede quedar como apoyo.
Implementación recomendada

Hacer híbrido:

reglas rápidas para casos obvios;
clasificador ligero LLM solo cuando no esté claro.

Ejemplo de salida:

{
  "input_type": "text",
  "actionability": "actionable",
  "possible_intent": "provide_fixed_schedule",
  "confidence": 0.92
}

## Extracción incremental de slots

Este es el salto importante.

No se procesa cada turno como “pregunta-respuesta cerrada”.
Procesa cada turno como “fuente de slots”.

Ejemplo
 
El agente pregunta:
“¿Cuál es tu nombre?”

El usuario responde:
“Soy Andrés Gómez, tengo 20 y voy en octavo.”

No debes decirle:
“Solo te pedí el nombre.”

Debes extraer:

full_name = Andrés Gómez
age = 20
semester = 8

y después preguntar solo lo faltante.

Flujo correcto

1. identificar intent principal;
2. extraer slots posibles;
3. fusionarlos con pending_entity_payload;
4. validar;
5. actualizar missing_fields_json;
6. preguntar solo lo que falta.

### Pseudoflujo
payload = merge(existing_payload, extracted_slots)
validated = validate(payload, domain_schema)
missing = get_missing_fields(validated, required_fields)

if missing:
    ask_only_for(missing[0] or grouped_missing)
else:
    move_to_confirmation_or_execution()

En este caso aplica muy bien a:

onboarding,
horario académico,
horario laboral,
actividades extracurriculares,
creación de actividad,
corrección de registro.

## Confirmación y ejecución

Esto sí viene después.

Aquí ya no se pregunta de más. Solo se ejecuta cuando:

el intent es claro,
los slots requeridos están completos,
la validación pasó,
si la acción es sensible, hubo confirmación.
Cuándo pedir confirmación

Se pide para:

crear o modificar eventos;
eliminar actividades;
guardar horario;
sincronizar calendario;
cambios que afecten agenda real.

No se pide para cada microdato.

Patrón ideal

Extracción → validación → resumen corto → confirmación → ejecución

Ejemplo:

Entendí esto:
- Materia: Cálculo
- Tipo: parcial
- Fecha: viernes
- Tiempo estimado: 3 horas

¿Lo programo así?
1. Sí
2. No

## Arquitectura recomendada para implementarlo

No se rehace todo el agente. Agrégale una capa previa.

Canal WhatsApp
   ↓
Buffer de mensajes
   ↓
Clasificador de entrada
   ↓
Router conversacional
   ↓
Extractor incremental de slots
   ↓
Gestor de estado conversacional
   ↓
Validador de dominio
   ↓
Confirmación / ejecución
   ↓
Servicios (DB, Outlook, To-Do, RAG)

### Qué sigue determinístico
validadores;
reglas de alcance;
reglas de activación;
CRUD;
sincronización;
detección de conflictos;
scoring del Radar.

### Qué se vuelve flexible
clasificación del mensaje;
extracción de slots;
interpretación de lenguaje natural;
redirección al alcance;
explicaciones pedagógicas.


