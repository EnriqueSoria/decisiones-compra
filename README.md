# Cuaderno de compras

Web estática en español para llevar un seguimiento de compras. Cada ficha
reúne los modelos que estás valorando, las fuentes de compra y tus notas.

## Editar el contenido

Copia una carpeta de ejemplo de `datos/` y ponle un nombre como
`cafetera-espresso`. El nombre se usa en la URL.

| Archivo | Contenido |
| --- | --- |
| `ficha.toml` | Título, categoría, estado y resumen. Es el único archivo obligatorio. |
| `opciones/*.toml` | Un archivo por opción, con enlace y campos opcionales de modelo, precio, estado y notas. |
| `fuentes.txt` | Un enlace HTTP o HTTPS por línea. |
| `notas.txt` | Criterios de compra o motivo de la decisión, en texto libre. |

Los estados de ficha son **Explorando**, **Comparando**, **Decidido** y
**Comprado**. Los estados de cada modelo admiten texto libre.

Guarda cada opción en un archivo como `opciones/01-modelo.toml`. Las
opciones se muestran por orden de nombre de archivo. El único campo
obligatorio es `url`, que debe ser un enlace HTTP o HTTPS. La tienda se
extrae del dominio, sin el prefijo `www.`. Escribe entre comillas los
valores que incluyas. Si omites `modelo`, se intenta usar el nombre del
producto o el título de la página, con el nombre del archivo como respaldo.
Si omites `precio`, se usa el publicado por la tienda en sus metadatos
si incluye importe y moneda. Si la página declara una imagen de vista previa
mediante Open Graph o Twitter Cards, se muestra junto al modelo. Puedes
añadir `imagen` con una URL absoluta de respaldo para cuando la vista
previa automática falte o no cargue.

## Caché local y actualización

En la primera generación, cada URL nueva se consulta una vez. Los títulos,
modelos, precios y fechas quedan en `cache/`. Los favicons y las fotos,
incluida la imagen de respaldo del TOML, se descargan en `cache/archivos/`.
El generador copia los recursos usados a `dist/`. Puedes abrir el cuaderno
sin conexión. Las siguientes generaciones solo consultan las URL nuevas.

Desde la carpeta del proyecto puedes ejecutar:

```bash
python build.py             # Reutiliza la caché.
python build.py --refresh   # Actualiza los metadatos y las fotos de producto.
python serve.py --refresh   # Actualiza al arrancar el servidor local.
```

Los favicons se comparten entre las fichas de cada tienda. Incluso con
`--refresh`, solo se descargan si falta una copia local.

Si una tienda falla, se conserva la última copia disponible. El precio de
caché lleva la fecha de su consulta. Si falla la primera descarga de un
dato o una imagen, usa `--refresh` para reintentarlo. Los valores de modelo
y precio escritos en el TOML siguen teniendo prioridad.

Ejemplo de opción:

```toml
modelo = "Modelo de ejemplo"
precio = "149,99 €"
url = "https://example.com/producto"
estado = "Finalista"
notas = "Confirmar las medidas."
```

En `fuentes.txt` se ignoran las líneas vacías. Cada fuente muestra su título
o, en su defecto, el dominio. Para el favicon se prueba primero DuckDuckGo,
después los iconos de la tienda y finalmente la inicial del dominio.

## Usar en local con Docker

Con Docker, el plugin Docker Compose y `just`, ejecuta desde la raíz del
proyecto:

```bash
just build       # Genera dist/ en la imagen decisiones-compra:generated.
just build --refresh  # Actualiza la caché local y regenera la imagen Docker.
just serve       # Arranca la web en 127.0.0.1:8000.
COMPRA_PORT=8080 just serve  # Arranca la web en otro puerto.
```

Abre [127.0.0.1:8000](http://127.0.0.1:8000). Mientras el servicio esté
en marcha, los cambios en `datos/`, `templates/` y `static/` regeneran
la web y recargan la página en el navegador. Docker Compose comparte la carpeta `cache/` con el proyecto y el servidor
recarga los datos si actualizas la caché. Si editas el código Python,
vuelve a ejecutar `just serve` con el puerto que estés usando para
reconstruir la imagen. Usa `docker compose down` para detener y retirar
el contenedor.

También puedes arrancar la web directamente con `docker compose up --build`.

## Publicar en GitHub Pages

1. Sube el contenido de esta carpeta, incluida `.github/`, a la raíz de tu repositorio.
2. En **Settings → Pages → Build and deployment → Source**, selecciona **GitHub Actions**.
3. En **Actions**, ejecuta **Publicar en GitHub Pages** desde la rama predeterminada
   o haz un push a esa rama.

Cada despliegue, por push o ejecución manual desde la rama predeterminada,
ejecuta las pruebas, genera la web con `python build.py --refresh` y
publica `dist/`. El repositorio incluye la caché para reutilizar los
favicons y recuperar los últimos datos disponibles si falla una tienda.
La URL aparece en el entorno `github-pages` de la ejecución. Los enlaces
relativos funcionan también cuando GitHub aloja la web en `/nombre-del-repo/`.
El contenido generado será visible para quienes tengan acceso al sitio de Pages.

[Documentación de GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)
