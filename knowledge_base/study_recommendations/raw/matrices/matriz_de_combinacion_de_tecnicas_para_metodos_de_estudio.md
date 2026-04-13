---
knowledge_type: technique_combination_matrix
document_type: matriz_de_combinacion
is_operational_method: false
matrix_id: matriz_de_combinacion_de_tecnicas_para_metodos_de_estudio
name: "Matriz de combinación de técnicas para métodos de estudio"
aliases: []
status: final
version: 1

objective_types:
  - comprension_profunda
  - memorizacion
  - autoevaluacion
  - organizacion
  - gestion_del_tiempo
  - repaso
  - transferencia
  - resolucion_de_problemas
  - preparacion_de_examen

best_for_activity_types:
  - quiz
  - parcial
  - lectura
  - toma_de_apuntes
  - repaso_semanal
  - resolucion_de_problemas

best_for_subject_types:
  - teorica
  - conceptual
  - mixta

best_for_student_profiles:
  - procrastinador
  - desorganizado
  - con_baja_concentracion
  - orientado_a_memoria
  - orientado_a_comprension

best_for_signals:
  - relee_mucho
  - no_se_autoevalua
  - olvida_rapido
  - se_distrae_facil
  - confunde_tipos_de_ejercicio
  - no_puede_explicar
  - procrastina
  - no_sostiene_sesiones_largas
  - necesita_estructura
  - siente_familiaridad_pero_no_recuerda

not_ideal_for_activity_types: []
not_ideal_for_subject_types: []
not_ideal_for_student_profiles: []
not_ideal_for_signals: []

included_techniques:
  - mapas_conceptuales
  - cornell
  - feynman
  - active_recall
  - repeticion_espaciada
  - interleaving
  - pomodoro
  - mnemotecnia

component_techniques:
  - mapas_conceptuales
  - cornell
  - feynman
  - active_recall
  - repeticion_espaciada
  - interleaving
  - pomodoro
  - mnemotecnia

optional_techniques:
  - pomodoro
  - mnemotecnia

excluded_techniques: []

primary_functions_covered:
  - comprension
  - sintesis
  - recuperacion
  - consolidacion
  - gestion_de_sesion
  - discriminacion
  - transferencia

develops:
  - comprension_profunda
  - memorizacion
  - autoevaluacion
  - organizacion
  - gestion_del_tiempo
  - repaso
  - transferencia
  - resolucion_de_problemas
  - preparacion_de_examen

combination_scope: "Matriz conceptual y operativa para comparar, combinar y priorizar técnicas de estudio frecuentes en estudiantes universitarios, especialmente en ingeniería de sistemas. No es un método completo ni una secuencia cerrada."

difficulty_level: intermedio
estimated_duration_days_min: 1
estimated_duration_days_max: 7
estimated_session_minutes_min: 25
estimated_session_minutes_max: 120

requires_prior_knowledge: true
requires_schedule_planning: true
requires_feedback: true
requires_materials:
  - material_base
  - preguntas
  - retroalimentacion
  - temporizador

adaptation_variables:
  - time_available
  - difficulty_level
  - activity_type
  - subject_type
  - student_profile
  - exam_proximity

works_best_alone: false
works_best_combined: true

recommended_combinations:
  - active_recall + repeticion_espaciada
  - interleaving + active_recall
  - cornell + active_recall
  - feynman + mapas_conceptuales
  - mnemotecnia + active_recall + repeticion_espaciada
  - pomodoro + tecnica_objetivo

contraindicated_combinations:
  - active_recall sin retroalimentacion
  - interleaving sin revision
  - mnemotecnia como eje de comprension
  - demasiadas tecnicas simultaneas

evidence_level: mixto
confidence_level: medio

primary_sources:
  - title: "Guía de repaso y preparación de exámenes"
    author: "COIE-UNED"
    year: no especificado
    source_type: guia_institucional
    url_or_reference: "Tipos de repaso, advertencias sobre empollar y valor de los repasos intermedios."

  - title: "Guía de metacognición sobre práctica espaciada y utilidad de técnicas"
    author: "EduCaixa"
    year: no especificado
    source_type: guia_educativa
    url_or_reference: "Definición de práctica espaciada, diferencias frente a estudio masivo y síntesis comparativa de utilidad de técnicas."

  - title: "Cómo utilizar la práctica de recuperación para mejorar el aprendizaje"
    author: "retrievalpractice.org / traducción Aptus"
    year: no especificado
    source_type: guia_educativa
    url_or_reference: "Definición de práctica de recuperación, rol de la retroalimentación y metacognición."

  - title: "Cómo usar la práctica de recuperación espaciada para potenciar el aprendizaje"
    author: "retrievalpractice.org / traducción Aptus"
    year: no especificado
    source_type: guia_educativa
    url_or_reference: "Relación explícita entre repetición espaciada y práctica de recuperación."

  - title: "Fascículo sobre técnica Feynman"
    author: "UnADM"
    year: no especificado
    source_type: material_academico
    url_or_reference: "Explicación de la técnica Feynman y aclaración de que se usa para comprender, no para memorizar."

  - title: "Fascículo sobre estudio intercalado"
    author: "UnADM"
    year: no especificado
    source_type: material_academico
    url_or_reference: "Definición de interleaving, prerrequisitos y necesidad de revisión."

  - title: "Técnica Pomodoro"
    author: "UAEH"
    year: no especificado
    source_type: guia_institucional
    url_or_reference: "Definición, pasos, ventajas y límites de Pomodoro."

  - title: "La técnica Pomodoro"
    author: "Francesco Cirillo"
    year: 2020
    source_type: libro
    url_or_reference: "Objetivos de foco, atención y reducción de interrupciones."

  - title: "Concept maps"
    author: "IHMC"
    year: no especificado
    source_type: documento_academico
    url_or_reference: "Características de mapas conceptuales: conceptos, enlaces, jerarquía y pregunta de enfoque."

  - title: "Estrategia: mapa conceptual"
    author: "UNED Costa Rica"
    year: no especificado
    source_type: guia_institucional
    url_or_reference: "Pasos y rasgos de mapas conceptuales."

  - title: "Método Cornell"
    author: "Universidad de Chile"
    year: no especificado
    source_type: guia_institucional
    url_or_reference: "Definición de Cornell y sus tres secciones."

  - title: "Mnemotecnia"
    author: "RAE y ANUIES"
    year: no especificado
    source_type: definicion_y_guia
    url_or_reference: "Definición normativa y ejemplo de uso como estrategia de memoria."

tags:
  - matriz_de_combinacion
  - tecnicas_de_estudio
  - combinaciones
  - ingenieria_de_sistemas
  - rag
  - grounding
  - chunking
  - active_recall
  - repeticion_espaciada
  - interleaving
  - pomodoro
  - mnemotecnia
---

# Matriz de combinación de técnicas para métodos de estudio

## 1. Definición breve
Este documento es una **matriz de combinación de técnicas**, no un método operativo completo. Compara ocho técnicas de estudio frecuentes y organiza su compatibilidad, su función dentro del estudio, sus prerrequisitos, sus riesgos y sus posibles sinergias para servir como base en la construcción futura de métodos de estudio.

## 2. Objetivo principal
Esta matriz busca:
- elegir combinaciones de técnicas según objetivo académico;
- evitar combinaciones ineficientes o mal ensambladas;
- guiar la construcción futura de métodos de estudio;
- detectar sinergias y riesgos entre técnicas;
- mejorar la decisión del agente cuando una sola técnica aislada no basta.

## 3. Qué cubre
La matriz cubre estas funciones del estudio:
- comprensión;
- síntesis;
- recuperación;
- consolidación;
- gestión de sesión;
- discriminación;
- transferencia.

## 4. Para qué sirve
Sirve cuando el sistema o el estudiante necesita decidir **qué técnicas conviene combinar** según:
- el objetivo académico;
- la actividad;
- el tipo de materia;
- el perfil del estudiante;
- las señales observables del problema.

También sirve para estructurar conocimiento en RAG sin confundir una técnica suelta con una combinación funcional.

## 5. Para qué no sirve tanto
- No reemplaza un método completo.
- No sustituye la investigación individual de cada técnica.
- No sirve sola para recomendar una secuencia cerrada si faltan señales del estudiante.
- No equivale a una receta universal.
- No determina automáticamente un plan de estudio semanal completo.

## 6. Problema que resuelve
Esta matriz está pensada para evitar que el agente recomiende técnicas aisladas sin criterio de integración, o que combine técnicas incompatibles para una tarea concreta. También busca evitar errores comunes como usar mnemotecnia donde el problema es comprensión, usar recuperación sin retroalimentación o mezclar demasiadas técnicas a la vez sin una función clara.

## 7. Prerrequisitos
Antes de usar esta matriz conviene tener:
- definidas las técnicas base;
- señales del estudiante o del contexto;
- claro el objetivo académico;
- un catálogo de variables homogéneo;
- material base sobre el cual practicar;
- posibilidad de generar preguntas y revisar respuestas;
- planificación mínima si se va a usar repetición espaciada.

## 8. Señales de que conviene usarla
- El problema no se resuelve bien con una sola técnica.
- El estudiante necesita cubrir varias funciones al mismo tiempo.
- Hay que integrar comprensión, recuperación y repaso.
- El sistema debe elegir entre varias combinaciones posibles.
- Se requiere traducir señales observables en combinaciones concretas.
- Se está construyendo un método a partir de piezas técnicas.

## 9. Señales de que no conviene usarla
- Ya existe un método cerrado y validado para el caso.
- Solo hay un cuello de botella muy puntual y claro.
- No hay información mínima sobre la actividad o el objetivo.
- Se necesita ejecución inmediata de una sola técnica ya seleccionada.
- Contextos específicos de no uso por actividad, materia o perfil: no especificado.

## 10. Tipo de estudiante o contexto al que más ayuda
Esta matriz ayuda más cuando el estudiante o contexto muestra:
- orientación a memoria;
- orientación a comprensión;
- baja concentración;
- desorganización;
- procrastinación.

También ayuda cuando el caso mezcla olvido, falta de autoevaluación y necesidad de estructura.

## 11. Tipo de actividad académica donde aporta más
- Quiz
- Parcial
- Lectura
- Toma de apuntes
- Repaso semanal
- Resolución de problemas

## 12. Tipo de materia donde aporta más
- Teórica
- Conceptual
- Mixta

## 13. Técnicas incluidas en la matriz
- Mapas conceptuales
- Cornell
- Feynman
- Práctica de recuperación (Active Recall)
- Repetición espaciada
- Práctica intercalada (Interleaving)
- Pomodoro
- Mnemotecnia

## 14. Técnicas excluidas o fuera de alcance
Esta matriz no desarrolla como técnicas centrales:
- relectura;
- subrayado;
- estudio masivo o empollar;
- otras técnicas no incluidas en las ocho técnicas base del documento.

Se mencionan solo como contraste o como prácticas de menor utilidad relativa, pero no forman parte del núcleo de combinación de esta matriz.

## 15. Rol funcional de cada técnica
- **Mapas conceptuales:** comprensión y síntesis de relaciones conceptuales.
- **Cornell:** toma de apuntes activa, síntesis y generación de preguntas.
- **Feynman:** comprensión profunda mediante explicación con palabras propias.
- **Práctica de recuperación:** recordar deliberadamente para fortalecer memoria, detectar huecos y apoyar autoevaluación.
- **Repetición espaciada:** consolidación y repaso distribuido para retención a largo plazo.
- **Interleaving:** discriminación entre tipos de problemas y elección de estrategia.
- **Pomodoro:** gestión de sesión, arranque, foco y ritmo de trabajo.
- **Mnemotecnia:** codificación de elementos discretos para facilitar recuerdo inicial.

## 16. Lógica de combinación
Las técnicas se comparan y combinan según:
- la función que cubren;
- sus prerrequisitos;
- su lugar típico dentro de una secuencia de estudio;
- sus riesgos de mal uso;
- su compatibilidad funcional con otras técnicas;
- el objetivo académico dominante.

La matriz no asume que todas las técnicas deban combinarse. La lógica es elegir pocas piezas, bien ensambladas, con funciones complementarias.

## 17. Criterios de compatibilidad
La escala utilizada es:
- **++ compatibilidad fuerte:** sinergia clara o recomendación explícita en las fuentes.
- **+ compatibilidad funcional:** combinación coherente y útil si se diseña bien.
- **± compatibilidad condicional:** útil solo bajo ciertas condiciones o con ciertos prerrequisitos.
- **— combinación de riesgo o poco recomendable:** alto riesgo de mal uso, redundancia o implementación contraproducente.

## 18. Matriz de compatibilidades

| Par de técnicas | Compatibilidad | Razón principal |
|---|---|---|
| Repetición espaciada + Active Recall | ++ | Es la combinación con soporte más explícito: recuperación espaciada. |
| Interleaving + Active Recall | ++ | Favorece discriminación, elección de estrategia y revisión con corrección. |
| Cornell + Active Recall | ++ | Cornell genera preguntas y resúmenes que alimentan la recuperación. |
| Feynman + Mapas conceptuales | + | Une explicación en palabras propias con organización relacional del contenido. |
| Mapas conceptuales + Active Recall | ± | Funciona si el mapa se transforma en preguntas y proposiciones correctas. |
| Feynman + Repetición espaciada | ± | Útil si Feynman se reserva para lagunas o ítems difíciles, no en cada repaso. |
| Pomodoro + cualquier técnica objetivo | ± | Pomodoro sirve como contenedor de sesión, pero no siempre conviene usarlo. |
| Mnemotecnia + Active Recall + Repetición espaciada | ± | Útil para listas o fórmulas, pero como complemento, no como eje central. |
| Active Recall sin retroalimentación | — | Puede reforzar errores y pierde una condición clave del uso correcto. |
| Interleaving sin revisión | — | Se pierde el mecanismo de corrección y aumenta el riesgo de consolidar fallos. |
| Mnemotecnia como sustituto de comprensión | — | Facilita recuerdo, pero no garantiza comprensión conceptual. |
| Demasiadas técnicas simultáneas | — | Aumenta carga cognitiva y vuelve irreal la planificación. |

## 19. Compatibilidades fuertes
Las compatibilidades más sólidas son:
- **Repetición espaciada + Active Recall:** es la combinación con soporte más explícito y mejor articulación entre consolidación y recuperación.
- **Interleaving + Active Recall:** es fuerte cuando el problema exige distinguir entre procedimientos o tipos de ejercicio.
- **Cornell + Active Recall:** es fuerte por diseño funcional, ya que Cornell produce preguntas y resúmenes que facilitan la recuperación.

## 20. Compatibilidades condicionales
Son útiles, pero no siempre:
- **Mapas conceptuales + Active Recall:** útil si el mapa está bien construido y luego se convierte en preguntas.
- **Feynman + Repetición espaciada:** útil si Feynman se usa para aclarar vacíos conceptuales y el espaciado se usa para consolidar.
- **Pomodoro + técnica objetivo:** útil si el problema principal es foco, arranque o interrupciones.
- **Mnemotecnia + Active Recall + Repetición espaciada:** útil para elementos discretos como listas, fórmulas o condiciones.

## 21. Combinaciones de riesgo o poco recomendables
Conviene evitar o usar con mucho cuidado:
- **Active Recall sin retroalimentación.**
- **Interleaving sin revisión.**
- **Mnemotecnia como eje de comprensión.**
- **Sobrecombinar técnicas sin una función clara.**

## 22. Orden típico de combinación
El orden típico de ensamblaje que sugiere el documento es:
1. Gestión de sesión  
2. Comprensión  
3. Síntesis  
4. Recuperación  
5. Consolidación  
6. Discriminación  
7. Transferencia  

Traducido a técnicas:
- **Pomodoro**
- **Feynman y/o Mapas conceptuales**
- **Cornell y/o Mapas conceptuales**
- **Active Recall**
- **Repetición espaciada**
- **Interleaving**
- **Feynman o Active Recall con preguntas de mayor nivel**

No es una secuencia cerrada, sino una plantilla de ensamblaje frecuente.

## 23. Recomendaciones por objetivo académico

### Si el objetivo es memorización
Priorizar:
- **Active Recall + Repetición espaciada**
- añadir **Mnemotecnia** solo si la información es discreta y difícil de recordar.

### Si el objetivo es comprensión profunda
Priorizar:
- **Feynman + Mapas conceptuales**
- añadir **Active Recall** para detectar huecos y verificar comprensión.

### Si el objetivo es preparación de examen
Priorizar:
- **Cornell + Active Recall + Repetición espaciada**
- añadir **Interleaving** si el examen mezcla tipos de preguntas o problemas.

### Si el objetivo es resolución de problemas
Priorizar:
- **Interleaving + Active Recall**
- añadir **Repetición espaciada** si el contenido debe mantenerse a mediano plazo.

## 24. Recomendaciones por actividad

### Si es quiz
- **Active Recall + Repetición espaciada**
- subir el nivel de preguntas y verificar respuestas.

### Si es parcial
- **Cornell + Active Recall + Repetición espaciada**
- añadir **Interleaving** si hay temas similares o procedimientos que se confunden.

### Si es proyecto
- no especificado.

### Si es lectura
- **Feynman + Mapas conceptuales** o **Cornell**
- luego convertir la síntesis en preguntas de recuperación.

### Si es toma de apuntes
- **Cornell**
- luego conectar con **Active Recall**.

### Si es repaso semanal
- **Active Recall + Repetición espaciada**

### Si es resolución de problemas
- **Interleaving + Active Recall**
- revisar estrategia y errores al final.

## 25. Recomendaciones por materia

### Bases de datos
- **Mapas conceptuales o Cornell + Active Recall + Interleaving**
- especialmente útil para distinguir formas normales o clasificar casos similares.

### Programación
- no especificado.

### Sistemas operativos
- **Feynman + Mapas conceptuales o Cornell + Active Recall + Repetición espaciada + Interleaving**
- útil para condiciones, estrategias y escenarios comparables.

### Redes
- **Mapas conceptuales o Cornell + Active Recall + Repetición espaciada**
- útil para capas, funciones, protocolos y relaciones.

### Otra
- Usar la matriz según objetivo, señales y actividad, no por nombre de materia solamente.

## 26. Recomendaciones por perfil del estudiante

### Perfil visual
- **Mapas conceptuales**
- combinar con **Active Recall** si además hay olvido rápido.

### Perfil analítico
- **Interleaving + Active Recall**
- especialmente si el problema exige distinguir entre procedimientos o categorías.

### Perfil procrastinador
- **Pomodoro + técnica objetivo**
- combinar con una técnica principal según el objetivo real.

### Perfil desorganizado
- **Cornell + Active Recall + Repetición espaciada**
- porque aporta estructura, preguntas y calendario de repaso.

### Perfil con_baja_concentracion
- **Pomodoro + Active Recall**
- priorizar sesiones cortas y verificables.

### Perfil orientado_a_memoria
- **Active Recall + Repetición espaciada**
- con **Mnemotecnia** como complemento si corresponde.

### Perfil orientado_a_comprension
- **Feynman + Mapas conceptuales**
- añadir **Active Recall** para comprobar comprensión.

## 27. Recomendaciones por señales observables

### Si relee mucho
Migrar desde relectura como eje hacia:
- **Active Recall + Repetición espaciada**
- usar **Cornell** o **Mapas conceptuales** solo como base para generar preguntas.

### Si olvida rápido
Priorizar:
- **Active Recall + Repetición espaciada**

### Si no se autoevalúa
Priorizar:
- **Active Recall**
- y asegurar retroalimentación después de responder.

### Si confunde tipos de ejercicio
Priorizar:
- **Interleaving + Active Recall**
- con revisión obligatoria.

### Si no puede explicar
Priorizar:
- **Feynman + Active Recall**

### Si se distrae fácil
Priorizar:
- **Pomodoro + técnica objetivo**

### Si procrastina
Priorizar:
- **Pomodoro**
- y enlazarlo con una técnica que produzca evidencia clara de avance.

### Si no sostiene sesiones largas
Priorizar:
- **Pomodoro + Active Recall**
- o sesiones breves de **Repetición espaciada**.

### Si necesita estructura
Priorizar:
- **Cornell + Repetición espaciada**
- y calendarizar la recuperación.

### Si siente familiaridad pero no recuerda
Priorizar:
- **Active Recall**
- y verificar con retroalimentación.

## 28. Errores comunes al usar la matriz
- Elegir demasiadas técnicas a la vez.
- Combinar técnicas sin una función clara para cada una.
- Pensar que mnemotecnia equivale a comprensión.
- Usar recuperación como castigo o prueba punitiva.
- Omitir la retroalimentación.
- Intercalar sin revisar.
- Querer convertir cualquier combinación en método completo sin más señales.

## 29. Señales de que la matriz está ayudando
- Las recomendaciones son más proporcionales al objetivo.
- Se combinan menos técnicas, pero con mejor función.
- Disminuye la dependencia de relectura y estudio masivo.
- Aumenta la presencia de recuperación y repaso distribuido.
- El agente distingue mejor entre comprensión, memoria y discriminación.
- Los errores típicos de combinación aparecen menos.

## 30. Señales de que hay que ajustarla
- Las recomendaciones siguen siendo demasiado generales.
- El sistema mezcla combinaciones funcionales con métodos completos.
- Aparecen muchas recuperaciones sin retroalimentación.
- Se recomienda Interleaving demasiado pronto o sin revisión.
- La matriz no logra discriminar por tipo de actividad o señal.
- Se detectan nuevas técnicas relevantes fuera de las ocho cubiertas.

## 31. Ejemplo aplicado en ingeniería de sistemas
- **Materia:** Sistemas Operativos
- **Actividad:** parcial teórico con casos
- **Objetivo:** recordar condiciones y distinguir estrategias de manejo
- **Técnicas evaluadas:** Feynman, Cornell, Active Recall, Repetición espaciada, Interleaving
- **Combinación elegida:** Feynman + Cornell + Active Recall + Repetición espaciada + Interleaving
- **Por qué:** combina comprensión inicial, síntesis estructurada, recuperación, consolidación y discriminación entre casos parecidos.
- **Resultado esperado:** mejor explicación del tema, menos olvido y mejor selección de estrategia en preguntas tipo caso.

## 32. Mini caso de uso
Un estudiante de Bases de Datos dice que entiende las formas normales cuando lee, pero luego las confunde en ejercicios y siente que “todo le suena familiar” aunque falla al responder.

Aplicación de la matriz:
- la señal dominante no es solo olvido, sino confusión entre casos;
- necesita distinguir criterios y comprobar si realmente recuerda;
- una sola técnica no basta.

Combinación sugerida:
- **Cornell** para sintetizar criterios;
- **Active Recall** para responder sin mirar;
- **Interleaving** para mezclar tablas parecidas;
- **Repetición espaciada** para mantener la distinción en el tiempo.

## 33. Regla operativa para el agente
Usar esta matriz cuando el estudiante necesite una recomendación de combinación entre técnicas y el problema no pueda resolverse con una sola técnica aislada. Priorizar combinaciones que cubran funciones distintas y evitar añadir técnicas sin una razón funcional clara. Si hay olvido, incluir recuperación; si hay olvido sostenido, añadir espaciado; si hay confusión entre ejercicios, añadir intercalado; si falta comprensión, añadir Feynman o una técnica de síntesis; si falta foco, usar Pomodoro como contenedor y no como técnica principal de aprendizaje.

## 34. Respuesta corta reusable para RAG
Esta matriz no es un método completo, sino una guía para combinar técnicas de estudio según su función. La combinación más sólida es **Active Recall + Repetición espaciada** para recordar mejor en el tiempo. Cuando además hay confusión entre ejercicios, conviene sumar **Interleaving**; si falta comprensión, conviene añadir **Feynman** o una técnica de síntesis como **Cornell** o **Mapas conceptuales**; y si el problema es foco, **Pomodoro** sirve como contenedor de la sesión.

## 35. Respuesta larga reusable para RAG
La matriz de combinación de técnicas para métodos de estudio organiza ocho técnicas frecuentes según lo que aportan, dónde encajan mejor dentro del estudio y con cuáles se combinan mejor. No debe leerse como un método cerrado, sino como una herramienta para ensamblar combinaciones funcionales. Su lógica principal es cubrir funciones distintas: comprensión, síntesis, recuperación, consolidación, discriminación, transferencia y gestión de sesión. La combinación con mejor respaldo es **Práctica de recuperación + Repetición espaciada**, porque une recordar deliberadamente con repaso distribuido. Cuando el estudiante confunde ejercicios o procedimientos, la mejor ampliación suele ser **Interleaving**, siempre con revisión. Cuando el problema es entender y explicar mejor, conviene sumar **Feynman** y, según el caso, **Mapas conceptuales** o **Cornell** para estructurar el contenido. **Mnemotecnia** se reserva como apoyo para listas o fórmulas y **Pomodoro** funciona como contenedor de ejecución si el problema es concentración o arranque. La utilidad de la matriz está en evitar combinaciones arbitrarias, seleccionar pocas técnicas con función clara y traducir señales observables en intervenciones más precisas dentro del RAG.

## 36. Evidencia resumida
La base de evidencia de esta matriz es **mixta**.

Tiene apoyo particularmente fuerte en:
- práctica de recuperación;
- repetición espaciada;
- uso de repaso intermedio;
- distinción entre técnicas de mayor utilidad y de menor utilidad relativa.

También tiene apoyo funcional en:
- Cornell como generador de preguntas y resumen;
- Feynman como técnica de comprensión;
- Interleaving como técnica de discriminación con revisión;
- Pomodoro como contenedor de sesión;
- mnemotecnia como apoyo puntual al recuerdo.

La combinación con mejor respaldo explícito es **Active Recall + Repetición espaciada**.  
Varias de las demás combinaciones tienen una base fuerte por mecanismo, pero no siempre cuentan con evidencia directa publicada en español para el par exacto. Por eso el nivel global de evidencia de la matriz es mixto y no uniforme en todas las combinaciones.

## 37. Nivel de confianza para el agente
**medio**

La confianza es media porque:
- la matriz está bien sustentada en funciones, prerrequisitos y riesgos de varias técnicas;
- existe una combinación central con respaldo especialmente fuerte;
- el documento diferencia entre combinaciones explícitamente apoyadas y combinaciones inferidas por mecanismo;

pero:
- no todas las combinaciones cuentan con evidencia directa equivalente;
- parte de la utilidad práctica depende del contexto, del objetivo y de la calidad de implementación;
- la matriz no reemplaza investigación específica de cada técnica ni un método cerrado.

## 38. Metadatos de recuperación sugeridos
- **matrix_id:** matriz_de_combinacion_de_tecnicas_para_metodos_de_estudio
- **knowledge_type:** technique_combination_matrix
- **document_type:** matriz_de_combinacion
- **is_operational_method:** false
- **objective_types:** comprension_profunda, memorizacion, autoevaluacion, organizacion, gestion_del_tiempo, repaso, transferencia, resolucion_de_problemas, preparacion_de_examen
- **activity_types:** quiz, parcial, lectura, toma_de_apuntes, repaso_semanal, resolucion_de_problemas
- **subject_types:** teorica, conceptual, mixta
- **student_profiles:** procrastinador, desorganizado, con_baja_concentracion, orientado_a_memoria, orientado_a_comprension
- **signals:** relee_mucho, no_se_autoevalua, olvida_rapido, se_distrae_facil, confunde_tipos_de_ejercicio, no_puede_explicar, procrastina, no_sostiene_sesiones_largas, necesita_estructura, siente_familiaridad_pero_no_recuerda
- **included_techniques:** mapas_conceptuales, cornell, feynman, active_recall, repeticion_espaciada, interleaving, pomodoro, mnemotecnia
- **component_techniques:** mapas_conceptuales, cornell, feynman, active_recall, repeticion_espaciada, interleaving, pomodoro, mnemotecnia
- **optional_techniques:** pomodoro, mnemotecnia
- **excluded_techniques:** no especificado
- **primary_functions_covered:** comprension, sintesis, recuperacion, consolidacion, gestion_de_sesion, discriminacion, transferencia
- **develops:** comprension_profunda, memorizacion, autoevaluacion, organizacion, gestion_del_tiempo, repaso, transferencia, resolucion_de_problemas, preparacion_de_examen
- **requires_prior_knowledge:** true
- **requires_schedule_planning:** true
- **requires_feedback:** true
- **requires_materials:** material_base, preguntas, retroalimentacion, temporizador
- **adaptation_variables:** time_available, difficulty_level, activity_type, subject_type, student_profile, exam_proximity
- **works_best_alone:** false
- **works_best_combined:** true
- **recommended_combinations:** active_recall + repeticion_espaciada; interleaving + active_recall; cornell + active_recall; feynman + mapas_conceptuales; mnemotecnia + active_recall + repeticion_espaciada; pomodoro + tecnica_objetivo
- **contraindicated_combinations:** active_recall sin retroalimentacion; interleaving sin revision; mnemotecnia como eje de comprension; demasiadas tecnicas simultaneas
- **difficulty_level:** intermedio
- **estimated_duration_days_min:** 1
- **estimated_duration_days_max:** 7
- **estimated_session_minutes_min:** 25
- **estimated_session_minutes_max:** 120
- **confidence_level:** medio
- **evidence_level:** mixto
