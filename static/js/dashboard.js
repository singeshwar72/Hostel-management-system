/* =====================================
        PAGE LOADER
===================================== */


window.addEventListener("load",()=>{

    const loader=document.getElementById("loader");

    if(loader){

        setTimeout(()=>{

            loader.style.opacity="0";

            loader.style.transition=".5s";


            setTimeout(()=>{

                loader.style.display="none";

            },500);


        },700);

    }

});






/* =====================================
        SIDEBAR CONTROL
===================================== */


const sidebar=document.getElementById("sidebar");

const menuBtn=document.getElementById("menuBtn");

const overlay=document.getElementById("overlay");



if(menuBtn){


menuBtn.addEventListener("click",()=>{


    if(window.innerWidth <= 900){


        sidebar.classList.toggle("mobile");

        overlay.classList.toggle("show");


    }

    else{


        sidebar.classList.toggle("collapsed");


    }


});


}






/* MOBILE OVERLAY CLOSE */


if(overlay){


overlay.addEventListener("click",()=>{


    sidebar.classList.remove("mobile");

    overlay.classList.remove("show");


});


}








/* =====================================
        LIVE CLOCK
===================================== */


function updateClock(){


    const now=new Date();



    let time=now.toLocaleTimeString("en-IN",{


        hour:"2-digit",

        minute:"2-digit",

        second:"2-digit",

        hour12:true


    });




    let date=now.toLocaleDateString("en-IN",{


        weekday:"long",

        day:"numeric",

        month:"long",

        year:"numeric"


    });




    const clock=document.getElementById("clock");

    const dateBox=document.getElementById("date");



    if(clock){

        clock.innerHTML=time;

    }



    if(dateBox){

        dateBox.innerHTML=date;

    }


}




updateClock();


setInterval(updateClock,1000);








/* =====================================
        DARK MODE
===================================== */


const themeBtn=document.getElementById("themeBtn");



if(localStorage.getItem("theme")=="dark"){


    document.body.classList.add("dark");


}





if(themeBtn){


themeBtn.addEventListener("click",()=>{


    document.body.classList.toggle("dark");



    if(document.body.classList.contains("dark")){


        localStorage.setItem("theme","dark");


        themeBtn.innerHTML=
        '<i class="fa-solid fa-sun"></i>';


    }

    else{


        localStorage.setItem("theme","light");


        themeBtn.innerHTML=
        '<i class="fa-solid fa-moon"></i>';


    }



});


}







/* =====================================
        ACTIVE MENU
===================================== */


const currentPage=window.location.pathname;


document.querySelectorAll(".menu a").forEach(link=>{


    if(link.getAttribute("href")===currentPage){


        link.classList.add("active");


    }


});









/* =====================================
        PROFILE DROPDOWN
===================================== */


const profileBtn=document.querySelector(".profile-btn");

const profileMenu=document.querySelector(".profile-menu");



if(profileBtn){


profileBtn.addEventListener("click",(e)=>{


    e.stopPropagation();


    profileMenu.style.display =

    profileMenu.style.display==="block"

    ? "none"

    : "block";


});


}








/* =====================================
        NOTIFICATION DROPDOWN
===================================== */


const notificationBtn=document.querySelector(".notification .icon-btn");

const notificationMenu=document.querySelector(".notification-menu");



if(notificationBtn){


notificationBtn.addEventListener("click",(e)=>{


    e.stopPropagation();


    notificationMenu.style.display =

    notificationMenu.style.display==="block"

    ? "none"

    : "block";


});


}








/* CLOSE DROPDOWNS */


document.addEventListener("click",()=>{


if(profileMenu){

profileMenu.style.display="none";

}



if(notificationMenu){

notificationMenu.style.display="none";

}


});







/* =====================================
        SMOOTH PAGE TRANSITION
===================================== */


document.querySelectorAll("a").forEach(link=>{


link.addEventListener("click",function(e){


    let href=this.getAttribute("href");


    if(
        href &&
        href.startsWith("/")
    ){


        document.body.style.opacity="0.7";


        document.body.style.transition=".3s";


    }


});


});








/* =====================================
        WINDOW RESIZE FIX
===================================== */


window.addEventListener("resize",()=>{


    if(window.innerWidth>900){


        sidebar.classList.remove("mobile");


        overlay.classList.remove("show");


    }


});