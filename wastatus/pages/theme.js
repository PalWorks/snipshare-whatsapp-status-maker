/* Before the first paint, so a page set to light does not flash dark on its way
   in. The tool page writes the same key. */
try {
  var choice = localStorage.getItem("wastatus.theme");
  if (choice === "light" || choice === "dark") {
    document.documentElement.dataset.theme = choice;
  }
} catch (e) { /* private mode */ }
