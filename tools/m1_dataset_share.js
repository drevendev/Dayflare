(function () {
  "use strict";
  const params = new URLSearchParams(window.location.search);
  const fields = ["df_dataset", "df_method", "df_end", "df_edition", "df_page"];
  if (!Array.from(params.keys()).some((key) => key.startsWith("df_"))) return;

  const status = document.getElementById("share-restore");
  const message = document.getElementById("share-message");
  if (!status || !message) return;
  const fail = (reason) => {
    status.style.display = "block";
    status.setAttribute("role", "alert");
    message.textContent = reason + " No different history has been substituted. Browse this dated snapshot below or open the archived version of your link.";
    status.focus();
  };
  if (Array.from(params.keys()).length !== fields.length ||
      fields.some((key) => params.getAll(key).length !== 1)) {
    fail("The shared link has missing, duplicate or unexpected fields.");
    return;
  }
  if (params.get("df_dataset") !== status.dataset.dataset ||
      params.get("df_method") !== status.dataset.method ||
      params.get("df_end") !== status.dataset.end) {
    fail("This link belongs to a different dataset, method or observation window.");
    return;
  }
  const edition = params.get("df_edition");
  const page = params.get("df_page");
  if (! (["en.wikipedia", "ru.wikipedia"].includes(edition)) ||
      !/^[1-9][0-9]{0,14}$/.test(page)) {
    fail("The shared edition or page identity is invalid.");
    return;
  }
  const id = "detail-" + edition.replaceAll(".", "-") + "-" + page;
  const detail = document.getElementById(id);
  if (!detail) {
    fail("This page identity is not available in the referenced snapshot.");
    return;
  }
  message.textContent = "Shared history verified for this exact dataset, method and UTC window.";
  const heading = detail.querySelector("h3");
  if (heading) {
    heading.setAttribute("tabindex", "-1");
    heading.focus({preventScroll: true});
  }
  detail.scrollIntoView();
})();
