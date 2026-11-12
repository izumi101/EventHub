// "Use" next to a test card fills the card form with that card and its documented details.
document.querySelectorAll('button.use-card').forEach(function (button) {
  button.addEventListener('click', function () {
    var fields = { pan: 'pan', exp_month: 'expMonth', exp_year: 'expYear', cvv: 'cvv', owner: 'owner' };
    Object.keys(fields).forEach(function (id) {
      var input = document.getElementById(id);
      if (input) input.value = button.dataset[fields[id]] || '';
    });
    var scroller = button.closest('.table-scroll');
    if (scroller) scroller.scrollLeft = 0;
    var pay = document.querySelector('form[action$="/card"] button[type="submit"]');
    if (pay) {
      pay.scrollIntoView({ block: 'center', behavior: 'smooth' });
      pay.focus({ preventScroll: true });
    }
  });
});
