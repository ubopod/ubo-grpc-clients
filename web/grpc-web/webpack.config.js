const path = require("path");

module.exports = {
  entry: "./src/client.ts",
  output: {
    filename: "main.js",
  },
  resolve: {
    extensions: [".ts", ".js"],
  },
  module: {
    rules: [
      {
        test: /\.ts$/,
        use: "ts-loader",
        exclude: /node_modules/,
      },
    ],
  },
  mode: "development",
  devServer: {
    static: path.join(__dirname, "static"),
    compress: true,
    port: 9000,
    hot: true,
    watchFiles: { paths: ["./src/client.ts"] },
  },
};
