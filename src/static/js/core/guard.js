(function () {
  // Po udanym logowaniu wróć tam, gdzie user chciał wejść
  window.addEventListener('login:success', () => {
    const back = sessionStorage.getItem('post_login_redirect') || '/';
    sessionStorage.removeItem('post_login_redirect');
    if (location.pathname !== back) window.location.href = back;
  });
})();