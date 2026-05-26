/* Redirect unauthenticated users to login — include before page scripts */
(function () {
  if (!localStorage.getItem('cr_access')) {
    const next = encodeURIComponent(window.location.pathname + window.location.search);
    window.location.replace('/login/?next=' + next);
  }
}());
