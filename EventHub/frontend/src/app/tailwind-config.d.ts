// tailwind.config.js is plain CommonJS; its spec reads it through this declaration.
declare module '*tailwind.config.js' {
  const config: unknown;
  export default config;
}
