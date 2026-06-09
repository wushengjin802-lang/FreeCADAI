export function currentRoutePrefix() {
  if (process.env.NEXT_PUBLIC_ROUTE_PREFIX) return process.env.NEXT_PUBLIC_ROUTE_PREFIX;
  if (typeof window !== "undefined" && window.location.pathname.startsWith("/freecadai")) {
    return "/freecadai";
  }
  return "";
}

export function routePath(path: string) {
  return `${currentRoutePrefix()}${path}`;
}
