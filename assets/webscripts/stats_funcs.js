function responsiveTopNav() {
    var x = document.getElementById("stTopnav");
    if (x.className === "topnav") {
      x.className += " responsive";
    } else {
      x.className = "topnav";
    }
  } 
  