import { defineConfig } from "cypress";
import createBundler from "@bahmutov/cypress-esbuild-preprocessor";
import { addCucumberPreprocessorPlugin } from "@badeball/cypress-cucumber-preprocessor";
import createEsbuildPlugin from "@badeball/cypress-cucumber-preprocessor/esbuild";

export default defineConfig({
    e2e: {
        specPattern: "**/*.feature",
        async setupNodeEvents(on, config) {
            await addCucumberPreprocessorPlugin(on, config);
            on(
                "file:preprocessor",
                createBundler({
                    plugins: [createEsbuildPlugin(config)],
                })
            );
            on("task", {
                log(message: string) {
                    console.log(message);
                    return null;
                },
            });
            return config;
        },
        baseUrl: "http://localhost:3000",
        defaultCommandTimeout: 10000,
        responseTimeout: 30000,
        pageLoadTimeout: 60000,
        video: true,
        screenshotOnRunFailure: true,
    },
});
