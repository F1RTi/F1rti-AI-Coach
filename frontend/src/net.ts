let token = location.hash.slice(1);
if (token) {
  sessionStorage.setItem("coach-access", token);
  history.replaceState(null, "", location.pathname);
} else token = sessionStorage.getItem("coach-access") || "";

export async function request(path: string, init: RequestInit = {}) {
  const response = await fetch("/api/" + path, {
    ...init,
    headers: { "x-coach-token": token, ...init.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw Error(
      typeof body.detail === "string"
        ? body.detail
        : response.status === 401
          ? "Откройте приложение из системного трея."
          : "Не удалось выполнить запрос · " + response.status,
    );
  }
  return response;
}
export async function get<T>(path: string): Promise<T> {
  return (await request(path)).json();
}
export async function post(path: string, data: unknown = {}) {
  return (
    await request(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    })
  ).json();
}
export async function download(path: string, name: string) {
  const blob = await (await request(path)).blob();
  const a = document.createElement("a"),
    url = URL.createObjectURL(blob);
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}
