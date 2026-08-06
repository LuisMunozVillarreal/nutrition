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
            const baseUrl = config.baseUrl || "http://localhost:3000"
            const graphqlEndpoint =
                process.env.NEXT_PUBLIC_GRAPHQL_ENDPOINT ||
                `${baseUrl}/graphql/`
            return {
                ...config,
                env: {
                    ...config.env,
                    NEXT_PUBLIC_GRAPHQL_ENDPOINT: graphqlEndpoint,
                },
            };
        },
        baseUrl: "http://localhost:3000",
        video: true,
    },
});
