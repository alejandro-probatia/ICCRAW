# Roadmap DCP + ICC Archivado

Este documento se conserva únicamente como registro histórico de una línea de
investigación que fue evaluada y después descartada como objetivo activo de la
serie 0.2.

## Estado

**Archivado. No implementar desde este roadmap.**

La decisión metodológica actual de ProbRAW es mantener un flujo principal basado
en:

1. revelado RAW reproducible;
2. perfil de ajuste por archivo;
3. perfil ICC de entrada generado desde referencias colorimétricas cuando hay
   carta;
4. perfiles ICC estándar reales cuando no hay carta;
5. gestión ICC del monitor limitada a la visualización;
6. trazabilidad mediante mochilas, manifiestos, ProbRAW Proof y C2PA opcional.

## Motivo

La integración DCP añadía una capa conceptual y técnica que no mejora el
propósito actual de la aplicación: producir salidas reproducibles, auditables y
colorimétricamente justificables a partir de referencias medibles.

Un DCP puede incluir componentes útiles en ciertos reveladores RAW, pero también
puede mezclar matrices, curvas tonales, tablas perceptuales y decisiones de
apariencia. Integrarlo en ProbRAW obligaría a definir políticas complejas sobre
qué partes aplicar, cómo combinarlas con el ICC de sesión y cómo evitar doble
corrección. Ese esfuerzo aumenta la superficie de error y puede debilitar la
claridad científica del flujo.

## Criterio Vigente

- DCP queda fuera del alcance activo de implementación.
- ICC sigue siendo el mecanismo formal de entrada/salida y validación.
- La carta de color y la referencia JSON son la base del perfilado avanzado.
- Sin carta, el flujo correcto es perfil manual + ICC estándar de salida.
- Cualquier soporte futuro de DCP deberá abrirse como investigación nueva,
  con validación propia, casos de uso claros y una decisión explícita de alcance.

## Documentos Vigentes

- [Roadmap principal](ROADMAP.es.md)
- [Metodología RAW e ICC](METODOLOGIA_COLOR_RAW.es.md)
- [Pipeline de color](COLOR_PIPELINE.es.md)
- [Manual de usuario](MANUAL_USUARIO.es.md)
