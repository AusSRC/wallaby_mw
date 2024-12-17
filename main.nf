#!/usr/bin/env nextflow

nextflow.enable.dsl = 2

process subfits {
    container = params.COMBINATION_IMAGE
    containerOptions = "--bind ${params.WORKDIR}:${params.CONTAINER_MOUNT}"
    input:
        val wallaby_image_filename
        val output_image_filename

    output:
        val "${params.CONTAINER_MOUNT}/$output_image", emit: subfits_image
        val true, emit: done

    script:
        """
        python3 /app/src/subfits.py \
            -i ${params.CONTAINER_MOUNT}/$wallaby_image_filename \
            -o ${params.CONTAINER_MOUNT}/$output_image_filename \
            -r
        """
}

process precombine {
    container = params.COMBINATION_IMAGE
    containerOptions = "--bind ${params.WORKDIR}:${params.CONTAINER_MOUNT}"
    input:
        val mwcombine_config
        val wallaby_image
        val combined_image
        val miriad_script
        val ready

    output:
        val true, emit: done

    script:
        """
        python3 /app/precombine.py \
            -c $mwcombine_config \
            -i $wallaby_image \
            -o ${params.CONTAINER_MOUNT}/$combined_image \
            -s ${params.CONTAINER_MOUNT}/$miriad_script
        """
}

process miriad {
    container = params.MIRIAD_IMAGE
    containerOptions = "--bind ${params.SCRATCH_ROOT}:${params.SCRATCH_ROOT}"

    input:
        val miriad_script
        val ready

    output:
        val true, emit: done

    script:
        """
        #!/bin/bash

        miriad $miriad_script
        """
}

// ---------------------------------------------------------------------------------------

workflow milkyway {
    take:
        wallaby_image
        mwcombine_config

    main:
        subfits(wallaby_image, params.SUBFITS_FILENAME)
        precombine(
            mwcombine_config,
            subfits.out.subfits_image,
            params.COMBINED_IMAGE_FILENAME,
            params.MIRIAD_SCRIPT_FILENAME,
            subfits.out.done
        )
}

workflow {
    main:
        milkyway(
            params.WALLABY_IMAGE,
            params.MWCOMBINE_CONFIG,
        )
}