const select = document.querySelector("#estado");
const cards = Array.from(document.querySelectorAll("[data-estado]"));
const empty = document.querySelector("#vacio");

select.closest(".filters").hidden = false;
select.addEventListener("change", () => {
  for (const card of cards) {
    card.hidden = Boolean(select.value && select.value !== card.dataset.estado);
  }
  empty.hidden = cards.some((card) => !card.hidden);
});
