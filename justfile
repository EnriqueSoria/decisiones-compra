set positional-arguments
export COMPRA_UID := `id -u`
export COMPRA_GID := `id -g`

# Genera la web con la caché del proyecto y empaqueta el resultado.
build *flags:
    docker compose run --build --rm web python build.py "$@"
    docker build --target generated --tag decisiones-compra:generated .

# Sirve la web con recarga automática.
serve:
    docker compose up --build

restart:
    docker compose restart web
