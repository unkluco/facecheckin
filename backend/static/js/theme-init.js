(() => {
    try {
      if (localStorage.getItem('facecheckin_theme') === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark');
      }
    } catch (e) {}
  })();
