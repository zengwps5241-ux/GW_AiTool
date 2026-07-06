const form = document.getElementById("form");
const err = document.getElementById("err");

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  err.textContent = "";
  const username = document.getElementById("username").value.trim();
  const password = document.getElementById("password").value;
  const res = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username, password }),
    credentials: "same-origin",
  });
  if (res.ok) {
    location.href = "/";
  } else {
    err.textContent = "账号或密码错误";
  }
});
