for (const image of document.querySelectorAll(".source-icon img")) {
  const icons = JSON.parse(image.dataset.icons);
  let nextIcon = 0;

  const tryNextIcon = () => {
    if (nextIcon < icons.length) {
      image.src = icons[nextIcon];
      nextIcon += 1;
    }
  };

  image.addEventListener("error", tryNextIcon);
  image.addEventListener("load", () => {
    image.classList.add("loaded");
    image.previousElementSibling.hidden = true;
  }, { once: true });
  tryNextIcon();
}

const viewer = document.querySelector(".photo-viewer");

for (const image of document.querySelectorAll("[data-previews]")) {
  const previews = JSON.parse(image.dataset.previews);
  const link = image.closest("a");
  let index = 0;

  const tryNextPreview = () => {
    index += 1;
    if (index < previews.length) {
      link.href = previews[index];
      image.src = previews[index];
    } else {
      link.hidden = true;
      link.nextElementSibling.hidden = false;
    }
  };

  image.addEventListener("error", tryNextPreview);
  if (image.complete && !image.naturalWidth) tryNextPreview();

  link.addEventListener("click", (event) => {
    if (!viewer?.showModal || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    const enlarged = viewer.querySelector("img");
    enlarged.src = link.href;
    enlarged.alt = image.alt;
    viewer.querySelector(".viewer-caption").textContent = image.alt;
    viewer.showModal();
  });
}

viewer?.addEventListener("click", (event) => {
  if (event.target === viewer) viewer.close();
});
