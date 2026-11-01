// AUTOPOST return to the shop: submit the form after pg_timeout_after_payment seconds.
document.querySelectorAll('form[data-autosubmit]').forEach(function (form) {
  var delay = parseInt(form.getAttribute('data-autosubmit'), 10) || 0;
  window.setTimeout(function () { form.submit(); }, delay * 1000);
});
